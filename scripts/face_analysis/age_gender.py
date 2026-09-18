#!/usr/bin/env python3
"""
age_gender.py — распознавание возраста и пола человека на фото.

Модели: InsightFace antelopev2 (SCRFD — детекция лиц, genderage — возраст/пол).
Если на фото не человек (лиц не найдено) — is_human: false.

Использование:
    python3 age_gender.py photo.jpg
    python3 age_gender.py photo1.jpg photo2.jpg ...   (несколько файлов)
    python3 age_gender.py photo.jpg --models-root /другой/путь

Выход — JSON на stdout:
{
  "image": "photo.jpg",
  "is_human": true,
  "faces_found": 1,
  "faces": [
    {"age": 31, "gender": "male", "gender_confidence": 0.999, "bbox": [x1,y1,x2,y2], "det_confidence": 0.92}
  ]
}

Коды выхода: 0 — успех (в т.ч. is_human=false), 2 — ошибка обработки файла.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

DEFAULT_MODELS_ROOT = "/opt/age_gender"  # модели лежат в {root}/models/antelopev2/
MODEL_NAME = "antelopev2"

GENDER_LABELS = {0: "female", 1: "male"}


def _patch_attribute_sex_score():
    """
    В новых версиях insightface Attribute.get() кладёт в face только gender/age,
    без sex_score (уверенности пола). Патчим метод, чтобы confidence был доступен.
    Если структура библиотеки изменилась — молча пропускаем (confidence будет null).
    """
    try:
        from insightface.model_zoo.attribute import Attribute
        from insightface.utils import face_align

        if getattr(Attribute, "_sex_score_patched", False):
            return

        def get(self, img, face):
            bbox = face.bbox
            w, h = (bbox[2] - bbox[0]), (bbox[3] - bbox[1])
            center = (bbox[2] + bbox[0]) / 2, (bbox[3] + bbox[1]) / 2
            rotate = 0
            _scale = self.input_size[0] / (max(w, h) * 1.5)
            aimg, M = face_align.transform(img, center, self.input_size[0], _scale, rotate)
            input_size = tuple(aimg.shape[0:2][::-1])
            blob = cv2.dnn.blobFromImage(aimg, 1.0 / self.input_std, input_size,
                                         (self.input_mean,) * 3, swapRB=True)
            pred = self.session.run(self.output_names, {self.input_name: blob})[0][0]
            if self.taskname == "genderage":
                gender = int(np.argmax(pred[:2]))
                age = int(np.round(pred[2] * 100))
                face["gender"] = gender
                face["age"] = age
                e = np.exp(pred[:2] - np.max(pred[:2]))  # softmax по логитам пола
                face["sex_score"] = e / e.sum()
                return gender, age
            return pred

        Attribute.get = get
        Attribute._sex_score_patched = True
    except Exception:
        pass


def build_app(models_root: str, det_size: int = 640):
    from insightface.app import FaceAnalysis

    _patch_attribute_sex_score()
    app = FaceAnalysis(
        name=MODEL_NAME,
        root=models_root,
        allowed_modules=["detection", "genderage"],
        providers=["CPUExecutionProvider"],
    )
    app.prepare(ctx_id=-1, det_size=(det_size, det_size))
    return app


def load_image(path: str) -> np.ndarray:
    data = np.fromfile(path, dtype=np.uint8)  # работает и с кириллицей в путях
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"не удалось прочитать изображение: {path}")
    return img


def process_image(app, path: str, min_det_conf: float = 0.5) -> dict:
    img = load_image(path)
    faces = app.get(img)

    result_faces = []
    for f in faces:
        if float(f.det_score) < min_det_conf:
            continue
        gender_code = int(f.gender)
        sex_score = getattr(f, "sex_score", None)
        gender_conf = round(float(np.max(sex_score)), 4) if sex_score is not None else None
        result_faces.append(
            {
                "age": int(f.age),
                "gender": GENDER_LABELS.get(gender_code, "unknown"),
                "gender_confidence": gender_conf,
                "bbox": [round(float(v), 1) for v in f.bbox],
                "det_confidence": round(float(f.det_score), 4),
            }
        )

    # самый уверенный — первым
    result_faces.sort(key=lambda x: x["det_confidence"], reverse=True)

    return {
        "image": path,
        "is_human": len(result_faces) > 0,
        "faces_found": len(result_faces),
        "faces": result_faces,
    }


def main():
    parser = argparse.ArgumentParser(description="Возраст и пол по фото (InsightFace)")
    parser.add_argument("images", nargs="+", help="пути к изображениям")
    parser.add_argument("--models-root", default=DEFAULT_MODELS_ROOT,
                        help=f"каталог с <name>/{MODEL_NAME}/scrfd_10g_bnkps.onnx и genderage.onnx")
    parser.add_argument("--det-size", type=int, default=640, choices=[320, 480, 640],
                        help="размер входа детектора (меньше = быстрее, хуже на мелких лицах)")
    parser.add_argument("--min-det-conf", type=float, default=0.5,
                        help="порог уверенности детектора лиц")
    args = parser.parse_args()

    t0 = time.time()
    try:
        app = build_app(args.models_root, args.det_size)
    except Exception as e:
        print(json.dumps({"error": f"не удалось загрузить модели: {e}"}, ensure_ascii=False))
        return 2

    results = []
    had_error = False
    for p in args.images:
        try:
            results.append(process_image(app, p, args.min_det_conf))
        except Exception as e:
            had_error = True
            results.append({"image": p, "is_human": None, "error": str(e)})

    payload = {
        "results": results,
        "elapsed_sec": round(time.time() - t0, 2),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
