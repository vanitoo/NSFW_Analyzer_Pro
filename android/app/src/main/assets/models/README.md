# Mobile ONNX models

Place exported mobile models here:

- `nsfw.onnx` — compact NSFW classifier;
- `general.onnx` — compact general image classifier.

The Android MVP deliberately builds and scans the gallery without model files.
When a model is present, `AnalyzerFactory` detects it automatically.

The exact ONNX input/output adapter will be added together with the chosen
mobile model export, because tensor names, normalization and label format
depend on the exported model.
