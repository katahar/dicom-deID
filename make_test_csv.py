import pandas as pd

def create_test_csv():
    data = {
        'MRN': ['12345', '67890', '_____'],
        'Accession': ['ACC001', 'ACC002', '99999'],
        'Long_Prefix': ['RS_Vessel_', 'RS_Vessel_', 'RS_Vessel_'],
        'Short_Prefix': ['RSV', 'RSV', 'RSV'],
        'Patient_Number': ['0001', '0002', '0003'],
        'New_Patient_ID': ['RS_Vessel_0001', 'RS_Vessel_0002', 'RS_Vessel_0003'],
        'Surgery_Date': ['2025-01-10', '2025-02-15', '2025-03-20'],
        'Anchor_Date': ['2024-06-15', '2024-06-15', '2024-06-15'],
        'Notes': ['First test patient', 'Patient with accession-only lookup', 'Test case: MRN padded with underscores']
    }
    df = pd.DataFrame(data)
    df.to_csv("test_mapping.csv", index=False)
    print("Created test_mapping.csv with the following patients:")
    print("  1. Patient RS_Vessel_0001: Normal MRN and Accession")
    print("  2. Patient RS_Vessel_0002: Will test accession number fallback")
    print("  3. Patient RS_Vessel_0003: Tests underscore padding handling")
    print(df.to_string())

if __name__ == "__main__":
    create_test_csv()