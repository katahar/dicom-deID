# dicom-deID
🏥 Medical Image De-identifier
A researcher-friendly tool for anonymizing DICOM scans while maintaining longitudinal timing.

This tool takes raw medical scans (DICOM files) and "scrubs" them of personal information. It replaces patient names and IDs with a research code (e.g., RS_01) and shifts all dates to a "fake" timeline so you can still tell how many days passed between scans without knowing the actual dates.

## 1. Prerequisites (One-time Setup)

Before using the script, you need to install Python and the necessary "libraries" (plugins) that allow the script to read medical data.

### Install Python
Download and install Python from [python.org](https://www.python.org).

**Important**: During installation, make sure to check the box that says "Add Python to PATH."

### Install Libraries
Open your computer's Terminal (Mac/Linux) or Command Prompt (Windows) and type the following command, then hit Enter:

```bash
pip install pydicom pandas dicom-anonymizer
```
## 2. Preparing Your Data

The script needs two things to work:

### A. The "Mapping" CSV File

Create an Excel sheet and save it as a .csv file. This is your "key" to link real patients to research IDs.

| Column | Example | Description |
|--------|---------|-------------|
| MRN (or first column) | 12345 | The original Patient ID found in the raw scans. Can be in any column name. |
| Accession (or second column) | ACC001 | The original Accession Number found in the raw scans. Can be in any column name. |
| New_Patient_ID | RS_01 | The anonymous name you want to give them (e.g., RS_Vessel_01). |
| Surgery_Date | 2025-01-10 | The actual date of their surgery (YYYY-MM-DD). |
| Anchor_Date | 2024-06-15 | (Optional) The "fake" surgery date for your project. If left blank, it defaults to June 15, 2024. |
| Notes | Study notes here | (Optional) Additional notes about the patient or scan. Will be embedded in DICOM metadata and saved as notes.txt. |

**Important:** If either MRN or Accession contains 5 or more underscores (e.g., `_____`), it will be treated as "no information provided" and the script will attempt to match using the other field.

### B. The Raw Data Folder

Put all your original patient folders into one main directory (e.g., a folder named Raw_Scans).

## 2b. Understanding the MRN/Accession Lookup Workflow

The script uses an intelligent fallback system to match patients from your DICOM files to your mapping CSV:

1. **Primary MRN Lookup**: First, it tries to match the DICOM's PatientID against the first column of your CSV.
2. **Accession Fallback**: If that fails, it tries to match the DICOM's AccessionNumber against the second column.
3. **Flipped Accession Check**: If both fail, it checks if the MRN value is actually in the Accession column (columns were swapped).
4. **Flipped MRN Check**: Finally, it checks if the Accession value is in the MRN column.

This approach handles cases where:
- You only have MRN or only have Accession Number
- The MRN and Accession fields are swapped in your data
- Either field contains `_____` (5+ underscores), treating it as missing data and using the other field

**Example**: If a DICOM has PatientID=`_____` and AccessionNumber=`12345`, the script will use the accession number to find the matching patient row.

## 3. How to Run the Script

1. Save the script provided to you as a file named `deid_tool.py`.
2. Open your Terminal or Command Prompt.
3. Navigate to the folder where you saved the script using the `cd` command (e.g., `cd Desktop/MyProject`).
4. Run the script using the following command format:

```bash
python deid_tool.py --csv [PATH_TO_CSV] --input [PATH_TO_RAW_DATA] --output [PATH_FOR_CLEAN_DATA]
```

### Real World Example

```bash
python deid_tool.py --csv mapping.csv --input ./Raw_Scans --output ./Anonymized_Data
```

## 4. What Happens Next?

Once the script starts, it will:

**Crawl**: Search through every folder in your input directory for DICOM files.

**Match Patient**: Use the MRN/Accession lookup workflow (see section 2b) to find the corresponding patient in your CSV.

**Anonymize**: Strip out the name and IDs, replacing them with the research ID from your CSV.

**Assign Accession**: Generate a new Accession Number as `New_Patient_ID_AccessionIndex` (e.g., `RS_01_1` for the first accession of patient RS_01).

**Add Notes**: If a Notes column exists, embed the notes in the DICOM's PatientComments field (tagged with `IMPORT_NOTES:`) and save them to `notes.txt` in the output directory.

**Time Shift**: Calculate how many days a scan was from the surgery and move that scan to the same relative position near your "Anchor Date."

**Preserve Clinical Data**: Maintain the following clinically relevant tags while anonymizing identifiers:
- SeriesDescription (scan type/name)
- Modality (imaging type: CT, MR, US, etc.)
- BodyPartExamined (anatomical region)
- ContrastAgent (if contrast was used)
- AcquisitionNumber (scan sequence number)
- PatientSex (biological sex)
- PatientAge (binned to 5-year intervals for privacy, e.g., age 43 → "040")

**Log**: Create a file named deid_log_[date].csv in your output folder. This is your audit trail showing exactly what was processed.

**Summary**: Display a final count of how many files were successfully cleaned, including pre-scan mapping details and directory transformations.

## 5. Directory Structure & Accession Numbering

### Input Structure
The script preserves your complete directory hierarchy. Directories are organized as: top-level (patient folders) and second-level (accession/session folders) with all deeper levels preserved.

```
raw_input/
├── Patient001/
│   ├── Accession001/
│   │   ├── DICOM/
│   │   │   └── file.dcm
│   │   └── notes.txt
│   ├── Accession002/
│   │   ├── DICOM/
│   │   │   └── file.dcm
│   │   └── SeriesInfo/
│   │       └── metadata.txt
│   └── Other_Number/
│       └── DICOM/
│           └── file.dcm
└── Patient002/
    └── Accession003/
        └── DICOM/
            ├── file1.dcm
            └── file2.dcm
```

### Output Structure
The output **preserves the same hierarchy**, but with anonymized directory names at top-level and second-level only:

```
deid_output/
├── RS_Vessel_01/           # Top-level: Patient001 → RS_Vessel_01 (from New_Patient_ID)
│   ├── RS_Vessel_01_1/     # Second-level: Accession001 → RS_Vessel_01_1 (1st accession)
│   │   ├── DICOM/          # Deeper levels preserved unchanged
│   │   │   └── file.dcm
│   │   └── notes.txt
│   ├── RS_Vessel_01_2/     # Second-level: Accession002 → RS_Vessel_01_2 (2nd accession)
│   │   ├── DICOM/
│   │   │   └── file.dcm
│   │   └── SeriesInfo/     # Deeper levels preserved unchanged
│   │       └── metadata.txt
│   └── RS_Vessel_01_3/     # Second-level: Other_Number → RS_Vessel_01_3 (3rd session)
│       └── DICOM/
│           └── file.dcm
└── RS_Vessel_02/           # Top-level: Patient002 → RS_Vessel_02
    └── RS_Vessel_02_1/     # Second-level: Accession003 → RS_Vessel_02_1
        └── DICOM/
            ├── file1.dcm
            └── file2.dcm

deid_log_20260204_144838.csv  # Audit trail
```

### Directory Renaming Rules

- **Top-level (Patient) directories**: Renamed to `New_Patient_ID` (e.g., RS_Vessel_01)
- **Second-level (Accession/Session) directories**: Renamed to `New_Patient_ID_N` where N is sequential (1, 2, 3, ...) based on alphabetical order
- **All deeper levels**: Preserved unchanged (DICOM/, SeriesInfo/, etc.)

This applies to ALL second-level directories, including:
- Actual accession number folders
- "Other" session folders (not matching MRN/Accession)
- Any other second-level organization

### Accession Number Format (DICOM Tags)

The tool generates accession numbers based on unique accession directories per patient:

| Component | Example | Rules |
|-----------|---------|-------|
| Patient ID | RS_Vessel_01 | From New_Patient_ID column |
| Accession Index | _1, _2, _3 | Sequential count of accessions per patient |
| Format | RS_Vessel_01_1 | `{New_Patient_ID}_{AccessionIndex}` |
| Max Length | 16 characters | DICOM SH VR limit; auto-truncated if longer |

**How it works:**
- First unique accession directory → `new_id_1`
- Second unique accession directory → `new_id_2`
- And so on...

This accession numbering is applied to:
- **DICOM PatientID tag**: `RS_Vessel_01`
- **DICOM AccessionNumber tag**: `RS_Vessel_01_1` (truncated to 16 chars if needed)
- **Output directory names**: `RS_Vessel_01_1/`, `RS_Vessel_01_2/`, etc.

## ⚠️ Troubleshooting & Tips

**"File not found"**: Ensure your file paths don't have spaces in them, or wrap the path in quotes (e.g., "/Users/name/Desktop/My Folder").

**"No mapping found"**: If a scan's MRN and Accession Number aren't in your CSV, or both contain `_____`, the script will skip that file and record an error in the log. Check the deid_log_[date].csv for details.

**Swapped fields**: If your MRN and Accession columns are reversed compared to what the script expects, the script will detect this and match them correctly. However, it's clearer to label your columns properly.

**Private Tags**: This script deletes "Private Tags" (extra data hidden by scanner manufacturers) to ensure maximum privacy for IRB compliance.