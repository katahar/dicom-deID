import os
import argparse
import pandas as pd
import pydicom
import time
from datetime import datetime, timedelta
from pathlib import Path
from dicomanonymizer import anonymize_dataset

def setup_logging(output_root):
    log_file = Path(output_root) / f"deid_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(log_file, 'w') as f:
        f.write("Timestamp,Original_File,MRN,New_ID,Calculated_Offset_Days,Status\n")
    return log_file

def log_event(log_path, data):
    with open(log_path, 'a') as f:
        f.write(f"{datetime.now().isoformat()},{data['file']},{data['mrn']},{data['id']},{data['offset']},{data['status']}\n")

def _get_column_case_insensitive(row, col_name):
    """
    Get a value from a pandas Series (row), matching column name case-insensitively.
    Returns the value if found, None otherwise.
    """
    col_lower = col_name.lower()
    for col in row.index:
        if col.lower() == col_lower:
            return row[col]
    return None

def _normalize_value(value):
    if value is None:
        return None
    value_str = str(value).strip()
    # Treat 5+ underscores as no info provided
    if len(value_str) >= 5 and all(c == '_' for c in value_str):
        return None
    return value_str if value_str else None

def _match_column(mapping_df, column, value):
    if value is None or column not in mapping_df.columns:
        return None
    mask = mapping_df[column].astype(str).str.strip() == value
    return mask if mask.any() else None

def _find_mapping_row(mapping_df, mrn_value, accession_value):
    columns = list(mapping_df.columns)
    if len(columns) < 2:
        raise ValueError("Mapping CSV must have at least two columns for MRN/Accession lookup")

    mrn_value = _normalize_value(mrn_value)
    accession_value = _normalize_value(accession_value)

    # Identify primary columns (first two), plus any named MRN/Accession columns if present
    primary_mrn_col = columns[0]
    primary_acc_col = columns[1]

    mrn_cols = [primary_mrn_col]
    acc_cols = [primary_acc_col]

    for named in ["MRN", "Mrn", "mrn"]:
        if named in mapping_df.columns and named not in mrn_cols:
            mrn_cols.append(named)

    for named in ["Accession", "AccessionNumber", "Accession_Number", "accession"]:
        if named in mapping_df.columns and named not in acc_cols:
            acc_cols.append(named)

    # 1) MRN lookup (preferred)
    for col in mrn_cols:
        mask = _match_column(mapping_df, col, mrn_value)
        if mask is not None:
            return mapping_df[mask].iloc[0], f"mrn:{col}"

    # 2) Accession lookup
    for col in acc_cols:
        mask = _match_column(mapping_df, col, accession_value)
        if mask is not None:
            return mapping_df[mask].iloc[0], f"accession:{col}"

    # 3) Flip and check for swapped values
    for col in acc_cols:
        mask = _match_column(mapping_df, col, mrn_value)
        if mask is not None:
            return mapping_df[mask].iloc[0], f"flipped_mrn_in_accession:{col}"

    for col in mrn_cols:
        mask = _match_column(mapping_df, col, accession_value)
        if mask is not None:
            return mapping_df[mask].iloc[0], f"flipped_accession_in_mrn:{col}"

    raise ValueError(
        f"No mapping found for MRN {mrn_value or 'N/A'} or Accession {accession_value or 'N/A'}"
    )

def _rebuild_directory_path(raw_path, output_root, input_root, mrn, accession, new_id, new_accession, parent_dir_map=None):
    """
    Rebuild directory structure, replacing:
    - MRN values with new_id
    - Accession values with new_accession
    - Directory parts containing underscores (likely patient names) with new_id
    - Sibling directories to MRN/Accession folders with new_id+"_other_session"
    - Other parts are preserved as-is
    
    parent_dir_map: dict mapping original parent directory paths to {"mrn": mrn, "accession": acc, "new_id": id, "sibling_dirs": [...]}
    """
    rel_path = raw_path.relative_to(input_root)
    parts = list(rel_path.parts)
    new_parts = []
    
    for i, part in enumerate(parts):
        # Check if this part is the filename (last part with .dcm)
        if part.lower().endswith('.dcm'):
            new_parts.append(part)
        # Check if part exactly matches MRN or Accession
        elif mrn and part == str(mrn):
            new_parts.append(new_id)
        elif accession and part == str(accession):
            new_parts.append(new_accession)
        # Check if part looks like a patient name (contains underscores and alphanumerics)
        elif '_' in part and any(c.isalpha() for c in part):
            new_parts.append(new_id)
        # Check if this directory is a sibling to MRN/Accession directory
        elif parent_dir_map:
            # Check if this is a "sibling" directory at the same level as MRN/Accession
            parent_path_so_far = input_root / Path(*parts[:i])
            if str(parent_path_so_far) in parent_dir_map:
                map_entry = parent_dir_map[str(parent_path_so_far)]
                if part in map_entry.get("sibling_dirs", []):
                    new_parts.append(f"{map_entry['new_id']}_other_session")
                else:
                    new_parts.append(part)
            else:
                new_parts.append(part)
        # Keep all other parts as-is
        else:
            new_parts.append(part)
    
    return output_root / Path(*new_parts)

def _build_directory_map(input_root):
    """
    Scan input directory to identify scan location folders and their siblings.
    Returns a map of parent directories to their MRN/Accession info and sibling folders.
    """
    dir_map = {}
    
    # Find all DICOM files and their parent directories
    for root, dirs, files in os.walk(input_root):
        for file in files:
            if file.lower().endswith('.dcm'):
                file_path = Path(root) / file
                rel_path = file_path.relative_to(input_root)
                
                # The parent directory containing the DICOM
                parent_dir = Path(root)
                parent_rel = parent_dir.relative_to(input_root)
                
                # Get the grandparent directory (one level up from immediate parent)
                if len(parent_rel.parts) > 0:
                    grandparent_path = input_root / Path(*parent_rel.parts[:-1]) if len(parent_rel.parts) > 1 else input_root
                    
                    # Track this directory and get its siblings
                    gp_str = str(grandparent_path)
                    if gp_str not in dir_map:
                        # Get all subdirectories in grandparent
                        try:
                            siblings = [d for d in os.listdir(grandparent_path) if os.path.isdir(os.path.join(grandparent_path, d))]
                            dir_map[gp_str] = {"sibling_dirs": siblings, "mrn": None, "accession": None, "new_id": None}
                        except:
                            pass
    
    return dir_map

def process_dicom(input_path, output_path, mapping_df, log_path, scan_number):
    try:
        # Load the file
        ds = pydicom.dcmread(input_path)
        mrn = _normalize_value(getattr(ds, "PatientID", None))
        accession = _normalize_value(getattr(ds, "AccessionNumber", None))

        # 1. Match MRN/Accession with fallback and flip checks
        row, _ = _find_mapping_row(mapping_df, mrn, accession)
        
        # 2. Setup IDs and Dates
        # Use case-insensitive lookup for all required columns
        new_id_val = _get_column_case_insensitive(row, 'New_Patient_ID')
        if new_id_val is None:
            raise ValueError(f"Column 'New_Patient_ID' not found in CSV. Available columns: {list(row.index)}")
        new_id = str(new_id_val)
        new_accession = f"{new_id}_{scan_number}"
        
        surgery_date_val = _get_column_case_insensitive(row, 'Surgery_Date')
        if surgery_date_val is None:
            raise ValueError(f"Column 'Surgery_Date' not found in CSV. Available columns: {list(row.index)}")
        actual_surgery = pd.to_datetime(surgery_date_val)
        
        # Get Anchor_Date with case-insensitive lookup, default if not found
        anchor_val = _get_column_case_insensitive(row, 'Anchor_Date')
        project_anchor = pd.to_datetime(anchor_val) if pd.notnull(anchor_val) else datetime(2024, 6, 15)
        
        # Get Notes with case-insensitive lookup
        notes = _get_column_case_insensitive(row, 'Notes')
        notes = str(notes).strip() if pd.notnull(notes) else ''
        
        # 3. Calculate Temporal Offset
        study_date_str = ds.StudyDate
        study_date_obj = datetime.strptime(study_date_str, '%Y%m%d')
        days_offset = (study_date_obj - actual_surgery).days
        
        # 4. Project onto Anchor
        shifted_date_obj = project_anchor + timedelta(days=days_offset)
        shifted_date_str = shifted_date_obj.strftime('%Y%m%d')

        # 5. Define Explicit Rules
        # We use a lambda that ignores the original value and returns our new one
        notes_content = f"IMPORT_NOTES: {notes}" if notes else ""
        patient_comments = f"Offset: {days_offset} days from surgery"
        if notes_content:
            patient_comments = f"{patient_comments}\n{notes_content}"
        
        custom_rules = {
            (0x0010, 0x0010): lambda dataset, tag: new_id,           # PatientName
            (0x0010, 0x0020): lambda dataset, tag: new_id,           # PatientID
            (0x0008, 0x0020): lambda dataset, tag: shifted_date_str, # StudyDate
            (0x0008, 0x0021): lambda dataset, tag: shifted_date_str, # SeriesDate
            (0x0008, 0x0050): lambda dataset, tag: new_accession,    # AccessionNumber
            (0x0010, 0x4000): lambda dataset, tag: patient_comments
        }

        # 6. RUN ANONYMIZATION
        # We pass the rules and set delete_private_tags to True
        anonymize_dataset(ds, custom_rules, delete_private_tags=True)
        
        # 7. MANUALLY FORCE CRITICAL TAGS (Double-check)
        # Sometimes libraries fail to overwrite; we'll do it manually to be safe
        ds.PatientName = new_id
        ds.PatientID = new_id
        ds.StudyDate = shifted_date_str
        ds.AccessionNumber = new_accession
        ds.PatientComments = patient_comments
        
        ds.save_as(output_path)
        
        # 8. Write notes.txt file in output directory
        if notes:
            notes_path = Path(output_path).parent / "notes.txt"
            with open(notes_path, 'w') as f:
                f.write(notes)
        
        log_event(log_path, {'file': input_path, 'mrn': mrn, 'id': new_id, 'offset': days_offset, 'status': 'SUCCESS'})
        return True, new_id
        
    except Exception as e:
        log_event(log_path, {'file': input_path, 'mrn': 'ERR', 'id': 'ERR', 'offset': 'ERR', 'status': f"ERROR: {str(e)}"})
        return False, None

def main():
    parser = argparse.ArgumentParser(description="De-identify DICOMs for Surgical Robotics Research")
    parser.add_argument("--csv", required=True, help="Path to the patient mapping CSV")
    parser.add_argument("--input", required=True, help="Root directory containing raw DICOMs")
    parser.add_argument("--output", required=True, help="Target directory for de-identified data")
    args = parser.parse_args()
    
    start_time = time.time()
    mapping_df = pd.read_csv(args.csv)
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    log_path = setup_logging(args.output)
    input_root = Path(args.input)
    
    # Build directory map to identify sibling directories
    parent_dir_map = _build_directory_map(input_root)
    
    # Summary Counters
    stats = {"success": 0, "fail": 0, "unique_patients": set()}
    patient_scan_count = {}  # Track scan number for each patient

    print(f"--- Starting Batch De-identification ---")
    print(f"Log File: {log_path}\n")

    for root, _, files in os.walk(args.input):
        for file in files:
            if file.lower().endswith('.dcm'):
                raw_path = Path(root) / file
                
                # First pass: determine patient ID and build anonymized directory path
                try:
                    ds_temp = pydicom.dcmread(str(raw_path))
                    mrn_temp = _normalize_value(getattr(ds_temp, "PatientID", None))
                    accession_temp = _normalize_value(getattr(ds_temp, "AccessionNumber", None))
                    row_temp, _ = _find_mapping_row(mapping_df, mrn_temp, accession_temp)
                    patient_id_temp = str(_get_column_case_insensitive(row_temp, 'New_Patient_ID'))
                    new_accession_temp = f"{patient_id_temp}_1"  # Placeholder for first pass
                    
                    # Rebuild output path with anonymized identifiers
                    target_path = _rebuild_directory_path(raw_path, output_root, input_root, mrn_temp, accession_temp, patient_id_temp, new_accession_temp, parent_dir_map)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Process with initial scan number
                    success, patient_id = process_dicom(str(raw_path), str(target_path), mapping_df, log_path, 1)
                    
                    if success:
                        # Update scan count and re-process with correct scan number
                        patient_scan_count[patient_id] = patient_scan_count.get(patient_id, 0) + 1
                        scan_number = patient_scan_count[patient_id]
                        
                        # Rebuild path with correct accession number
                        new_accession_final = f"{patient_id}_{scan_number}"
                        target_path = _rebuild_directory_path(raw_path, output_root, input_root, mrn_temp, accession_temp, patient_id, new_accession_final, parent_dir_map)
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        success, patient_id = process_dicom(str(raw_path), str(target_path), mapping_df, log_path, scan_number)
                    
                    if success:
                        stats["success"] += 1
                        stats["unique_patients"].add(patient_id)
                    else:
                        stats["fail"] += 1
                except Exception as e:
                    log_event(log_path, {'file': str(raw_path), 'mrn': 'ERR', 'id': 'ERR', 'offset': 'ERR', 'status': f"ERROR: {str(e)}"})
                    stats["fail"] += 1

    # Final Summary Report
    duration = time.time() - start_time
    print(f"\n--- Processing Summary ---")
    print(f"Total Time:         {duration:.2f} seconds")
    print(f"Files Processed:    {stats['success']}")
    print(f"Files Failed:       {stats['fail']}")
    print(f"Unique Patients:    {len(stats['unique_patients'])}")
    print(f"Output Directory:   {args.output}")
    print(f"--------------------------")

if __name__ == "__main__":
    main()