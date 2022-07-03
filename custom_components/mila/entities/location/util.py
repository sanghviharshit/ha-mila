
POLLEN_INDEX_MAPPING={
    "None": 0,
    "Low": 1,
    "Moderate": 2,
    "High": 3,
    "VeryHigh": 4
}

def to_pollen_index(value: str):
    try:
        return POLLEN_INDEX_MAPPING[value]
    except:
        return None