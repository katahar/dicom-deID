import pandas as pd

def create_test_csv():
    data = {
        'MRN': ['12345'],
        'New_Patient_ID': ['RS_Vessel_01'],
        'Surgery_Date': ['2025-01-10'],  # This scan (Jan 1) is 9 days BEFORE surgery
        'Anchor_Date': ['2024-06-15']   # We expect the output date to be June 6, 2024
    }
    df = pd.DataFrame(data)
    df.to_csv("test_mapping.csv", index=False)
    print("Created test_mapping.csv")

if __name__ == "__main__":
    create_test_csv()