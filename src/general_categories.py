from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneralCategory:
    kind: str
    category: str
    subcategory: str
    prompt: str


GENERAL_CATEGORIES: tuple[GeneralCategory, ...] = (
    # Documents
    GeneralCategory("Документ", "Документы", "Паспорт", "a clear photo or scan of a passport"),
    GeneralCategory("Документ", "Документы", "Удостоверение личности", "a photo or scan of an identity card"),
    GeneralCategory("Документ", "Документы", "Чек", "a photo or scan of a store receipt"),
    GeneralCategory("Документ", "Документы", "Счёт / инвойс", "a photo or scan of an invoice or bill"),
    GeneralCategory("Документ", "Документы", "Договор", "a photo or scan of a contract document"),
    GeneralCategory("Документ", "Документы", "Сертификат", "a photo or scan of a certificate or diploma"),
    GeneralCategory("Документ", "Документы", "Текстовый документ", "a photo or scan of a text document page"),

    # Screenshots / digital content
    GeneralCategory("Скриншот", "Цифровое", "Интерфейс программы", "a screenshot of a desktop software application"),
    GeneralCategory("Скриншот", "Цифровое", "Веб-страница", "a screenshot of a website or web browser"),
    GeneralCategory("Скриншот", "Цифровое", "Мессенджер / чат", "a screenshot of a chat or messenger conversation"),
    GeneralCategory("Скриншот", "Цифровое", "Код / терминал", "a screenshot of source code or a terminal window"),
    GeneralCategory("Скриншот", "Цифровое", "Игра", "a screenshot from a video game"),

    # People
    GeneralCategory("Фото", "Люди", "Портрет", "a portrait photo of one person"),
    GeneralCategory("Фото", "Люди", "Группа людей", "a photo of a group of people"),
    GeneralCategory("Фото", "Люди", "Семья", "a family photo"),

    # Nature
    GeneralCategory("Фото", "Природа", "Горы", "a landscape photo of mountains"),
    GeneralCategory("Фото", "Природа", "Море / океан", "a landscape photo of the sea or ocean"),
    GeneralCategory("Фото", "Природа", "Пляж", "a photo of a beach"),
    GeneralCategory("Фото", "Природа", "Лес", "a landscape photo of a forest"),
    GeneralCategory("Фото", "Природа", "Река / озеро", "a landscape photo of a river or lake"),
    GeneralCategory("Фото", "Природа", "Закат / рассвет", "a landscape photo of a sunset or sunrise"),
    GeneralCategory("Фото", "Природа", "Снег / зима", "a snowy winter landscape"),

    # Transport
    GeneralCategory("Фото", "Транспорт", "Автомобиль", "a photo of a car"),
    GeneralCategory("Фото", "Транспорт", "Мотоцикл", "a photo of a motorcycle"),
    GeneralCategory("Фото", "Транспорт", "Самолёт", "a photo of an airplane"),
    GeneralCategory("Фото", "Транспорт", "Поезд", "a photo of a train"),
    GeneralCategory("Фото", "Транспорт", "Корабль / лодка", "a photo of a ship or boat"),

    # Animals
    GeneralCategory("Фото", "Животные", "Кошка", "a photo of a cat"),
    GeneralCategory("Фото", "Животные", "Собака", "a photo of a dog"),
    GeneralCategory("Фото", "Животные", "Птица", "a photo of a bird"),
    GeneralCategory("Фото", "Животные", "Дикие животные", "a photo of a wild animal"),

    # Food
    GeneralCategory("Фото", "Еда", "Еда / блюдо", "a photo of food or a prepared dish"),
    GeneralCategory("Фото", "Еда", "Напиток", "a photo of a drink or beverage"),

    # Architecture / interiors
    GeneralCategory("Фото", "Архитектура", "Здание", "a photo of a building or architecture"),
    GeneralCategory("Фото", "Архитектура", "Город / улица", "a city street photo"),
    GeneralCategory("Фото", "Архитектура", "Интерьер", "a photo of an indoor room or interior"),

    # Objects
    GeneralCategory("Фото", "Предметы", "Электроника", "a photo of an electronic device or computer hardware"),
    GeneralCategory("Фото", "Предметы", "Одежда", "a photo of clothing or fashion items"),
    GeneralCategory("Фото", "Предметы", "Домашний предмет", "a photo of a household object"),

    # Graphics / internet
    GeneralCategory("Графика", "Графика", "Рисунок / иллюстрация", "a drawing, illustration, or digital artwork"),
    GeneralCategory("Графика", "Графика", "Мем", "an internet meme with text"),
    GeneralCategory("Графика", "Графика", "Инфографика", "an infographic or diagram"),
)


GENERAL_KINDS = tuple(dict.fromkeys(item.kind for item in GENERAL_CATEGORIES))
GENERAL_GROUPS = tuple(dict.fromkeys(item.category for item in GENERAL_CATEGORIES))
