# NSFW Analyzer Pro

**NSFW Analyzer Pro** — локальное настольное приложение на Python/Tkinter для пакетного анализа изображений и сортировки потенциально NSFW-контента.

Текущая версия: **2.4.0**.

## Возможности

- рекурсивное сканирование папки с изображениями;
- анализ без отправки пользовательских изображений в сторонний API;
- поддержка JPG/JPEG, PNG, BMP и GIF (для GIF анализируется первый кадр);
- несколько NSFW-backend'ов;
- настраиваемый порог классификации;
- фильтры: все, НЮ, безопасные, неопределённые и BAD;
- превью, открытие оригинала, удаление и перемещение файлов;
- сохранение структуры подпапок при перемещении;
- защита от коллизий имён при перемещении;
- фоновое сканирование и анализ без прямого доступа worker-потоков к Tkinter;
- журнал `analyzer_nu.log`.

## Модели

| Модель | Назначение |
| --- | --- |
| Yahoo NSFW / OpenNSFW2 | Бинарный NSFW-классификатор на TensorFlow/Keras |
| Marqo Fast | Лёгкий ViT-классификатор SFW/NSFW (~22 MB); PyTorch, CUDA auto |
| Freepik 4-Level | EVA-классификатор `neutral / low / medium / high` (~173 MB); PyTorch, CUDA auto |
| NudeNet Detector | YOLOv8/ONNX detector открытых частей тела; возвращает классы детекций |
| GantMan NSFW | Официальный GantMan 1.2.0 `saved_model.tflite`; категории `drawings / hentai / neutral / porn / sexy`; TensorFlow Lite CPU |
| NSFW Hub Detector | NSFW-классификатор из TensorFlow Hub |

Обычный ImageNet MobileNetV2 и общий OpenImages TF Hub backend удалены из выбора: они не являются NSFW-классификаторами и давали несопоставимые с остальными моделями результаты.

> Результат модели — вероятностная оценка, а не безошибочное решение. Для важных сценариев проверяйте пограничные результаты вручную и подбирайте порог на своих данных.

## Требования

- Python 3.11+
- TensorFlow **2.20.0**
- Keras 3.10+

OpenNSFW2 0.19+ используется через Keras 3 backend. TensorFlow закреплён на 2.20.0 — той же ветке runtime, которую использует актуальная конфигурация OpenNSFW2.

Дополнительные модели используют PyTorch/Transformers/timm/NudeNet. Они перечислены в `requirements-models.txt`.

## Когда скачиваются модели

Выбор модели в ComboBox **ничего не скачивает**. Сканирование папки также **не загружает модель**.

Модель инициализируется только после нажатия **«Анализировать»**:

- **Marqo Fast** — при первом анализе скачивает веса с Hugging Face; дальше использует локальный cache;
- **Freepik 4-Level** — аналогично, скачивает веса с Hugging Face при первом анализе;
- **Yahoo/OpenNSFW2** — веса скачиваются при первом фактическом предсказании, если их ещё нет;
- **GantMan** — при первом анализе скачивается официальный release 1.2.0 (~100 MB); из него используется готовый `saved_model.tflite`, который затем хранится в `~/.cache/nsfw-analyzer-pro/gantman/1.2.0`;
- **NSFW Hub** — скачивается TensorFlow Hub при первом анализе;
- **NudeNet 320n** — веса уже входят в пакет `nudenet`, поэтому отдельной загрузки при анализе нет.

Hugging Face cache для приложения хранится в `~/.cache/nsfw-analyzer-pro/huggingface`; TensorFlow Hub и OpenNSFW2 также используют подпапки `~/.cache/nsfw-analyzer-pro`. Поэтому после первого запуска веса повторно не скачиваются, пока cache не удалён.

## NVIDIA GPU

Для Windows + NVIDIA используйте:

```bat
START_NVIDIA.cmd
```

`START_NVIDIA.cmd` устанавливает CUDA 12.8-сборку PyTorch и `onnxruntime-gpu==1.26.0` для CUDA 12.x. **Marqo Fast** и **Freepik 4-Level** автоматически используют CUDA, если `torch.cuda.is_available()` возвращает `True`. В логе приложения показывается фактически выбранное устройство и название GPU.

NudeNet работает через ONNX Runtime. NVIDIA-скрипт заменяет CPU-пакет `onnxruntime` на GPU-сборку и приложение автоматически выбирает `CUDAExecutionProvider`, если он доступен.

**GantMan 1.2.0 теперь не использует legacy SavedModel/Keras:** приложение запускает официальный `saved_model.tflite` через TensorFlow Lite/XNNPACK на CPU. Это устраняет зависимость GantMan от старого Keras SavedModel API, но не добавляет ему CUDA на native Windows.

Важно для Windows: TensorFlow 2.11+ больше не поддерживает CUDA на native Windows. Поэтому Yahoo и NSFW Hub с TensorFlow 2.20.0 обычно работают на CPU под обычным Windows. Для TensorFlow + NVIDIA официальный путь — WSL2. PyTorch-модели Marqo/Freepik и ONNX-модель NudeNet этой проблемы на native Windows не имеют.

## Быстрый запуск в Windows

```bat
git clone https://github.com/vanitoo/NSFW_Analyzer_Pro.git
cd NSFW_Analyzer_Pro
START.cmd
```

`START.cmd` создаёт `.venv`, устанавливает/обновляет зависимости из `requirements.txt` и запускает приложение.

## Ручная установка

```bash
git clone https://github.com/vanitoo/NSFW_Analyzer_Pro.git
cd NSFW_Analyzer_Pro
python -m venv .venv
```

Активация окружения:

```bash
# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

Установка и запуск:

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-models.txt
python main.py
```

После установки проекта как пакета также доступна команда:

```bash
nsfw-analyzer
```

## Использование

1. Нажмите **«Обзор»** и выберите папку.
2. Выберите модель и порог. По умолчанию порог — `0.70`.
3. Нажмите **«Анализировать»**.
4. Отфильтруйте результаты.
5. При необходимости переместите текущую выборку кнопкой **«Переместить»** или выбранные строки клавишей `F6`.

Горячие клавиши:

- `Enter` — открыть выбранное изображение;
- `F6` — переместить выбранные изображения по текущему фильтру;
- `Delete` — удалить выбранные файлы.

При перемещении используются подпапки `NU`, `BAD` и `UNKNOWN`. Они исключаются из последующих сканирований, чтобы уже отсортированные изображения не анализировались повторно.

## Структура

```text
.
├── main.py                    # минимальная точка входа
├── src/
│   ├── __init__.py            # пакет приложения
│   ├── ui.py                  # Tkinter UI
│   ├── scanner.py             # фоновое сканирование файлов
│   ├── analyzer.py            # маршрутизация моделей и анализ
│   ├── models_legacy.py       # Yahoo/GantMan/TF runtime helpers
│   ├── models_extra.py        # Marqo / Freepik / NudeNet
│   └── utils.py               # общие утилиты и логирование
├── requirements.txt           # базовые зависимости
├── requirements-models.txt    # Marqo / Freepik / NudeNet
├── pyproject.toml             # метаданные пакета и Ruff
├── START.cmd                  # обычный запуск под Windows
└── START_NVIDIA.cmd           # запуск с CUDA PyTorch для NVIDIA
```

Старые каталоги `v1/` и `v3/` удалены: их история остаётся доступна в Git, а рабочая реализация теперь находится только в `src/`.

## Что изменено в 2.4

- рабочие модули перенесены из корня в пакет `src/`; в корне оставлен только `main.py`;
- удалены архивные каталоги `v1/` и `v3/`;
- импорты переведены на пакетные относительные импорты, а packaging обновлён под новую структуру;
- TensorFlow закреплён на **2.20.0** вместо широкого диапазона версий;
- GantMan переведён с legacy Keras `TFSMLayer`/SavedModel на официальный `saved_model.tflite` из release 1.2.0;
- GantMan больше не скачивает плавающий `master.zip`: используется фиксированный официальный release;
- TensorFlow больше не импортируется при старте `analyzer.py`; он загружается лениво только для соответствующих backend'ов;
- NVIDIA launcher устанавливает `onnxruntime-gpu==1.26.0` для CUDA 12.x и проверяет доступные ONNX providers;
- NudeNet предварительно загружает CUDA/cuDNN DLLs ONNX Runtime, когда это поддерживается.

## Что изменено в 2.3

- добавлены Marqo Fast, Freepik 4-Level и NudeNet Detector;
- добавлено автоматическое определение NVIDIA CUDA для PyTorch-моделей;
- в лог выводится фактическое устройство inference;
- добавлен `START_NVIDIA.cmd` для установки CUDA-сборки PyTorch;
- добавлен локальный cache Hugging Face для повторного использования весов;
- ограничена параллельность GPU-backend'ов для защиты VRAM.

## Что изменено в 2.2

- исправлена смена модели: backend теперь действительно переинициализируется;
- устранена гонка при одновременной инициализации модели несколькими worker'ами;
- worker-потоки больше не читают и не изменяют Tk widgets напрямую;
- результат всех NSFW-моделей унифицирован до `✓ / ✗ / BAD`;
- TensorFlow-декодирование работает не только с JPEG, но и с PNG/BMP/GIF;
- исправлена синхронизация `all_files` после анализа, удаления и перемещения;
- перемещение сохраняет структуру подпапок и не перезаписывает одноимённые файлы;
- исправлен `pyproject.toml`: команда `nsfw-analyzer` теперь указывает на существующую `main()`;
- `requirements.txt` и `pyproject.toml` синхронизированы;
- удалён накопившийся дублированный рабочий код из root-модулей.

## Лицензии сторонних моделей

Код NSFW Analyzer Pro распространяется под MIT, но сторонние модели и библиотеки имеют собственные лицензии. В частности, у NudeNet есть несогласованность метаданных: его `setup.py` указывает MIT, тогда как файл `LICENSE` в репозитории содержит GNU AGPL-3.0. Перед распространением сборки, особенно коммерческим, проверьте требования лицензий используемых моделей и зависимостей.

## Лицензия

MIT. См. `LICENSE`.
