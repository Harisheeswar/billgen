def map_ocr_gst(gst_val):
    val = round(gst_val)
    if val in [0, 5, 12, 18, 28]:
        return float(val)
    
    if str(val).endswith('8'):
        return 18.0
    if str(val).endswith('2'):
        return 12.0
        
    standard_slabs = [0.0, 5.0, 12.0, 18.0, 28.0]
    return min(standard_slabs, key=lambda x: abs(x - gst_val))

# Test cases
test_cases = [48.0, 8.0, 18.0, 5.0, 12.0, 2.0, 0.0]
for tc in test_cases:
    print(f"Input: {tc} -> Corrected: {map_ocr_gst(tc)}")
