# dicom-deID
🏥 Medical Image De-identifier
A researcher-friendly tool for anonymizing DICOM scans while maintaining longitudinal timing.

This tool takes raw medical scans (DICOM files) and "scrubs" them of personal information. It replaces patient names and IDs with a research code (e.g., RS_01) and shifts all dates to a "fake" timeline so you can still tell how many days passed between scans without knowing the actual dates.

1. Prerequisites (One-time Setup)
Before using the script, you need to install Python and the necessary "libraries" (plugins) that allow the script to read medical data.

Install Python: Download and install Python from python.org.

Important: During installation, make sure to check the box that says "Add Python to PATH."

Install Libraries: Open your computer's Terminal (Mac/Linux) or Command Prompt (Windows) and type the following command, then hit Enter:

Bash
pip install pydicom pandas dicom-anonymizer
2. Preparing Your Data
The script needs three things to work:

A. The "Mapping" CSV File

Create an Excel sheet and save it as a .csv file. This is your "key" to link real patients to research IDs.

MRN	New_Patient_ID	Surgery_Date	Anchor_Date
12345	RS_01	2025-01-10	2024-06-15
67890	RS_02	2025-02-15	2024-06-15
MRN: The original Patient ID found in the raw scans.

New_Patient_ID: The anonymous name you want to give them (e.g., Patient_A).

Surgery_Date: The actual date of their surgery (YYYY-MM-DD).

Anchor_Date: (Optional) The "fake" surgery date for your project. If left blank, it defaults to June 15, 2024.

B. The Raw Data Folder

Put all your original patient folders into one main directory (e.g., a folder named Raw_Scans).

3. How to Run the Script
Save the script provided to you as a file named deid_tool.py.

Open your Terminal or Command Prompt.

Navigate to the folder where you saved the script using the cd command (e.g., cd Desktop/MyProject).

Run the script using the following command format:

Bash
python deid_tool.py --csv [PATH_TO_CSV] --input [PATH_TO_RAW_DATA] --output [PATH_FOR_CLEAN_DATA]
Real World Example:

Bash
python deid_tool.py --csv mapping.csv --input ./Raw_Scans --output ./Anonymized_Data
4. What Happens Next?
Once the script starts, it will:

Crawl: Search through every folder in your input directory for DICOM files.

Anonymize: Strip out the name and MRN, replacing them with the IDs from your CSV.

Time Shift: Calculate how many days a scan was from the surgery and move that scan to the same relative position near your "Anchor Date."

Log: Create a file named deid_log_[date].csv in your output folder. This is your audit trail showing exactly what was processed.

Summary: Display a final count of how many files were successfully cleaned.

⚠️ Troubleshooting & Tips
"File not found": Ensure your file paths don't have spaces in them, or wrap the path in quotes (e.g., "/Users/name/Desktop/My Folder").

"MRN not found": If a scan's MRN isn't in your CSV, the script will skip that file and record an error in the log.

Private Tags: This script deletes "Private Tags" (extra data hidden by scanner manufacturers) to ensure maximum privacy for IRB compliance.