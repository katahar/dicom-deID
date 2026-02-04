import os
from pydicom import dcmread
from pydicom.data import get_testdata_file
from pathlib import Path
from datetime import datetime

def setup_test_environment():
    # 1. Get the official pydicom test file
    sample_path = get_testdata_file("CT_small.dcm")
    
    # Create raw input directory structure
    input_dir = Path("./raw_input")
    input_dir.mkdir(exist_ok=True)
    
    # Test Case 1: Normal MRN + Accession lookup with directory structure
    print("\n=== Test Case 1: Normal MRN and Accession with multiple accessions ===")
    
    # First accession
    patient_dir = input_dir / "patient_12345"
    accession_dir = patient_dir / "ACC001" / "DICOM"
    accession_dir.mkdir(parents=True, exist_ok=True)
    
    ds = dcmread(sample_path)
    ds.PatientName = "Doe^John"
    ds.PatientID = "12345"
    ds.AccessionNumber = "ACC001"
    ds.PatientSex = "M"
    ds.PatientAge = "045"  # Will be binned to "040"
    ds.SeriesDescription = "CT Head"
    ds.Modality = "CT"
    ds.BodyPartExamined = "HEAD"
    ds.ContrastAgent = ""
    ds.AcquisitionNumber = "1"
    ds.StudyDate = "20250101"  # Jan 1, 2025 (9 days before surgery)
    test_file_path = accession_dir / "CT_image_1.dcm"
    ds.save_as(str(test_file_path))
    print(f"✅ Created: {test_file_path}")
    print(f"   Directory structure: patient_12345/ACC001/DICOM/")
    print(f"   PatientID: {ds.PatientID} → RS_Vessel_01")
    print(f"   AccessionNumber: {ds.AccessionNumber} → RS_Vessel_01_1")
    print(f"   PatientAge: {ds.PatientAge} → 040 (binned)")
    print(f"   Clinical tags preserved: Modality={ds.Modality}, BodyPartExamined={ds.BodyPartExamined}")
    
    # Second accession (different directory)
    accession_dir = patient_dir / "Other_Session" / "DICOM"
    accession_dir.mkdir(parents=True, exist_ok=True)
    
    ds = dcmread(sample_path)
    ds.PatientName = "Doe^John"
    ds.PatientID = "12345"
    ds.AccessionNumber = "ACC002"  # Different accession
    ds.PatientSex = "M"
    ds.PatientAge = "045"
    ds.SeriesDescription = "CT Chest"
    ds.Modality = "CT"
    ds.BodyPartExamined = "CHEST"
    ds.ContrastAgent = "Contrast"
    ds.AcquisitionNumber = "2"
    ds.StudyDate = "20250115"  # Jan 15, 2025
    test_file_path = accession_dir / "CT_image_2.dcm"
    ds.save_as(str(test_file_path))
    print(f"✅ Created: {test_file_path}")
    print(f"   Directory structure: patient_12345/Other_Session/DICOM/")
    print(f"   AccessionNumber: {ds.AccessionNumber} → RS_Vessel_01_2 (second accession)")
    print(f"   Expected output directory: RS_Vessel_01/RS_Vessel_01_2/DICOM/")
    
    # Test Case 2: Accession-only lookup (MRN is underscores)
    print("\n=== Test Case 2: Accession number fallback (MRN has underscores) ===")
    patient_dir = input_dir / "patient_67890"
    accession_dir = patient_dir / "ACC002" / "DICOM"
    accession_dir.mkdir(parents=True, exist_ok=True)
    
    ds = dcmread(sample_path)
    ds.PatientName = "Smith^Jane"
    ds.PatientID = "_____"  # Should be ignored, will use accession
    ds.AccessionNumber = "ACC002"
    ds.PatientSex = "F"
    ds.PatientAge = "032"  # Will be binned to "030"
    ds.SeriesDescription = "MRI Brain"
    ds.Modality = "MR"
    ds.BodyPartExamined = "BRAIN"
    ds.ContrastAgent = ""
    ds.AcquisitionNumber = "1"
    ds.StudyDate = "20250220"  # Feb 20, 2025 (5 days after surgery)
    test_file_path = accession_dir / "MRI_image_1.dcm"
    ds.save_as(str(test_file_path))
    print(f"✅ Created: {test_file_path}")
    print(f"   PatientID: {ds.PatientID} (will be ignored - 5+ underscores)")
    print(f"   AccessionNumber: {ds.AccessionNumber} (used for lookup)")
    print(f"   PatientSex: {ds.PatientSex} (preserved)")
    print(f"   Expected output AccessionNumber: RS_Vessel_02_1")
    
    # Test Case 3: Underscore-padded MRN (fallback scenario)
    print("\n=== Test Case 3: Underscore-padded MRN with accession fallback ===")
    patient_dir = input_dir / "patient_99999"
    accession_dir = patient_dir / "accession_99999" / "DICOM"
    accession_dir.mkdir(parents=True, exist_ok=True)
    
    ds = dcmread(sample_path)
    ds.PatientName = "Brown^Charlie"
    ds.PatientID = "_____"  # Padded with underscores
    ds.AccessionNumber = "99999"
    ds.PatientSex = "M"
    ds.PatientAge = "060"  # Will be binned to "060"
    ds.SeriesDescription = "Ultrasound"
    ds.Modality = "US"
    ds.BodyPartExamined = "ABDOMEN"
    ds.ContrastAgent = ""
    ds.AcquisitionNumber = "1"
    ds.StudyDate = "20250320"  # Mar 20, 2025
    test_file_path = accession_dir / "US_image_1.dcm"
    ds.save_as(str(test_file_path))
    print(f"✅ Created: {test_file_path}")
    print(f"   PatientID: {ds.PatientID} (5+ underscores, treated as missing)")
    print(f"   AccessionNumber: {ds.AccessionNumber} (used for matching)")
    print(f"   Modality: {ds.Modality} (preserved)")
    print(f"   Expected output AccessionNumber: RS_Vessel_03_1")
    
    print("\n" + "="*70)
    print("Test environment setup complete!")
    print("\nTest Summary:")
    print("  ✓ Directory structure: top-level (patient) and second-level (accession)")
    print("  ✓ Multiple accessions per patient")
    print("  ✓ 'Other' session directories (renamed to patient_id_N)")
    print("  ✓ Clinical tags: SeriesDescription, Modality, BodyPartExamined, Contrast")
    print("  ✓ Sex preservation and age binning (5-year intervals)")
    print("  ✓ MRN/Accession fallback scenarios")
    print("\nRun the following command to test the de-identification:")
    print("\npython deid_tool.py --csv test_mapping.csv --input ./raw_input --output ./deid_output")
    print("\nExpected results:")
    print("  - 4 DICOM files should be processed")
    print("  - Directory structure preserved: RS_Vessel_01/RS_Vessel_01_1/, RS_Vessel_01/RS_Vessel_01_2/, etc.")
    print("  - AccessionNumbers follow pattern: New_Patient_ID_AccessionIndex")
    print("  - PatientAge binned: 045→040, 032→030, 060→060")
    print("  - Clinical tags maintained in output DICOMs")
    print("="*70 + "\n")

if __name__ == "__main__":
    setup_test_environment()