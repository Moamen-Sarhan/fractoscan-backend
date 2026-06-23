from ultralytics import YOLO

model = YOLO("best.pt")

FRACTURE_CLASSES = [
    "Comminuted",
    "Greenstick",
    "Healthy",
    "Oblique Displaced",
    "Oblique",
    "Spiral",
    "Transverse Displaced",
    "Transverse"
]

CLASS_COLORS = {
    "Healthy":              (0, 255, 120),
    "Comminuted":           (0, 60, 255),
    "Greenstick":           (0, 200, 255),
    "Oblique":              (255, 180, 0),
    "Oblique Displaced":    (255, 100, 0),
    "Spiral":               (180, 0, 255),
    "Transverse":           (0, 180, 255),
    "Transverse Displaced": (255, 0, 80),
}