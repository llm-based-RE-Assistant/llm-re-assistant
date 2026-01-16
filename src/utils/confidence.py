def calculate_confidence(num_issues):
    confidence = 1.0 - (num_issues * 0.15)
    return max(confidence, 0.0)

