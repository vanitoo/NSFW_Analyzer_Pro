# NSFW Analyzer Pro

**NSFW Analyzer Pro** — локальное настольное приложение на Python/Tkinter для пакетного анализа изображений и сортировки потенциально NSFW-контента.

Текущая версия: **2.3.0**.

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
| GantMan NSFW | Категории `drawings / hentai / neutral / porn / sexy`; TensorFlow/Keras |
| NSFW Hub Detector | NSFW-классификатор из TensorFlow Hub |

Обычный ImageNet MobileNetV2 и общий OpenImages TF Hub backend удалены из выбора: они не являются NSFW-классификаторами и давали несопоставимые с остальными моделями результаты.

> Результат модели — вероятностная оценка, а не безошибочное решение. Для важных сценариев проверяйте пограничные результаты вручную и подбирайте порог на своих данных.

## Требования

- Python 3.11+
- TensorFlow 2.16+
- Keras 3

OpenNSFW2 0.19+ используется через Keras 3 backend.

Дополнительные модели используют PyTorch/Transformers/timm/NudeNet. Они перечислены в `requirements-models.txt`.

## Когда скачиваются модели

Выбор модели в ComboBox **ничего не скачивает**. Сканирование папки также **не загружает модель**.

Модель инициализируется только после нажатия **«Анализировать»**:

- **Marqo Fast** — при первом анализе скачивает веса с Hugging Face; дальше использует локальный cache;
- **Freepik 4-Level** — аналогично, скачивает веса с Hugging Face при первом анализе;
- **Yahoo/OpenNSFW2** — веса скачиваются при первом фактическом предсказании, если их ещё нет;
- **GantMan** — скачивается и распаковывается при первом анализе;
- **NSFW Hub** — скачивается TensorFlow Hub при первом анализе;
- **NudeNet 320n** — веса уже входят в пакет `nudenet`, поэтому отдельной загрузки при анализе нет.

Hugging Face cache для приложения хранится в `~/.cache/nsfw-analyzer-pro/huggingface`; TensorFlow Hub и OpenNSFW2 также используют подпапки `~/.cache/nsfw-analyzer-pro`. Поэтому после первого запуска веса повторно не скачиваются, пока cache не удалён.

## NVIDIA GPU

Для Windows + NVIDIA используйте:

```bat
START_NVIDIA.cmd
```

Скрипт устанавливает CUDA-сборку PyTorch и затем остальные зависимости. **Marqo Fast** и **Freepik 4-Level** автоматически используют CUDA, если `torch.cuda.is_available()` возвращает `True`. В логе приложения показывается фактически выбранное устройство и название GPU.

NudeNet работает через ONNX Runtime. По умолчанию пакет использует CPU; если установлен совместимый `onnxruntime-gpu` и доступен `CUDAExecutionProvider`, приложение автоматически переключает NudeNet на CUDA.

Важно для Windows: TensorFlow 2.11+ больше не поддерживает CUDA на native Windows. Поэтому Yahoo/GantMan/NSFW Hub с текущим TensorFlow обычно работают на CPU под обычным Windows. Для TensorFlow + NVIDIA официальный путь — WSL2. PyTorch-модели Marqo/Freepik этой проблемы на native Windows не имеют.

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
├── main.py           # точка входа и console script
├── ui.py             # Tkinter UI; вся работа с Tk выполняется в main thread
├── scanner.py        # фоновое сканирование файлов
├── analyzer.py       # модели и многопоточный анализ
├── utils.py          # общие утилиты и логирование
├── requirements.txt         # базовые зависимости
├── requirements-models.txt  # Marqo / Freepik / NudeNet
├── pyproject.toml           # метаданные пакета и Ruff
├── START.cmd                # обычный запуск под Windows
├── START_NVIDIA.cmd         # запуск с CUDA PyTorch для NVIDIA
├── v1/               # архив ранней реализации
└── v3/               # экспериментальный рефакторинг
```

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

## Лицензия

MIT. См. `LICENSE`.
