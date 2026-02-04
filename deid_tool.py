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

def process_dicom(input_path, output_path, mapping_df, log_path, scan_number):
    try:
        # Load the file
        ds = pydicom.dcmread(input_path)
        mrn = _normalize_value(getattr(ds, "PatientID", None))
        accession = _normalize_value(getattr(ds, "AccessionNumber", None))

        # 1. Match MRN/Accession with fallback and flip checks
        row, _ = _find_mapping_row(mapping_df, mrn, accession)
        
        # 2. Setup IDs and Dates
        new_id = str(row['New_Patient_ID'])
        new_accession = f"{new_id}_{scan_number}"
        actual_surgery = pd.to_datetime(row['Surgery_Date'])
        anchor_val = row.get('Anchor_Date')
        project_anchor = pd.to_datetime(anchor_val) if pd.notnull(anchor_val) else datetime(2024, 6, 15)
        notes = row.get('Notes', '') or ''
        notes = str(notes).strip()
        
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
    
    # Summary Counters
    stats = {"success": 0, "fail": 0, "unique_patients": set()}
    patient_scan_count = {}  # Track scan number for each patient

    print(f"--- Starting Batch De-identification ---")
    print(f"Log File: {log_path}\n")

    for root, _, files in os.walk(args.input):
        for file in files:
            if file.lower().endswith('.dcm'):
                raw_path = Path(root) / file
                rel_path = raw_path.relative_to(args.input)
                target_path = output_root / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # First pass to get patient ID
                success, patient_id = process_dicom(str(raw_path), str(target_path), mapping_df, log_path, 1)
                
                if success:
                    # Update scan count and re-process with correct scan number
                    patient_scan_count[patient_id] = patient_scan_count.get(patient_id, 0) + 1
                    scan_number = patient_scan_count[patient_id]
                    success, patient_id = process_dicom(str(raw_path), str(target_path), mapping_df, log_path, scan_number)
                
                if success:
                    stats["success"] += 1
                    stats["unique_patients"].add(patient_id)
                else:
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