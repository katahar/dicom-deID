import pandas as pd

def create_test_csv():
    data = {
        'MRN': ['12345', '67890', '_____'],
        'Accession': ['ACC001', 'ACC002', '99999'],
        'New_Patient_ID': ['RS_Vessel_01', 'RS_Vessel_02', 'RS_Vessel_03'],
        'Surgery_Date': ['2025-01-10', '2025-02-15', '2025-03-20'],
        'Anchor_Date': ['2024-06-15', '2024-06-15', '2024-06-15'],
        'Notes': ['First test patient', 'Patient with accession-only lookup', 'Test case: MRN padded with underscores']
    }
    df = pd.DataFrame(data)
    df.to_csv("test_mapping.csv", index=False)
    print("Created test_mapping.csv with the following patients:")
    print("  1. Patient RS_Vessel_01: Normal MRN and Accession")
    print("     - Tests standard MRN/Accession lookup")
    print("     - Tests directory mapping (top-level → RS_Vessel_01)")
    print("     - Tests accession directory naming (second-level → RS_Vessel_01_1)")
    print("     - Tests clinical tag preservation (Modality, BodyPartExamined, etc.)")
    print("     - Tests sex preservation and age binning")
    print("  2. Patient RS_Vessel_02: Will test accession number fallback")
    print("     - Tests accession-based lookup when MRN is unavailable")
    print("     - Tests 'other' directory handling (second-level renaming)")
    print("  3. Patient RS_Vessel_03: Tests underscore padding handling")
    print("     - Tests underscore-padded MRN detection (5+ underscores = missing)")
    print("     - Tests fallback to accession number matching")
    print(df.to_string())

if __name__ == "__main__":
    create_test_csv()