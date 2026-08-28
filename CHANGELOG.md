# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Додаючи рослину, бот сам каже, що це: надсилаєш фото — він пропонує назву, латину, ритм поливу й кілька
  слів про те, що саме цю рослину найчастіше вбиває. Один дотик «Так, це воно» — і два питання майстра вже
  не задаються. Не впізнав — так і каже, а не вигадує

## [0.4.0] - 2026-08-28

### Added

- Фотографування приймає кілька кадрів за раз. Перший — загальний, з того самого боку, що й минулого разу;
  далі скільки завгодно крупних планів листя, де раніше з'являються шкідники та плями

### Fixed

- Фотографування більше не втрачає кадри. Інструкція просить загальний кадр і крупні плани листя, а бот
  зберігав лише перший і мовчки викидав решту альбому — тепер приймає всі
- Порівняння «було-стало» на сторінці рослини й огляд від ШІ беруть тільки загальні кадри. Раніше крупний
  план листя міг потрапити в порівняння проти знімка всієї рослини, і виходила вигадана «зміна»

## [0.3.0] - 2026-08-28

- Room climate is its own module instead of a part of plant care. The air-conditioner card and the weather
  digest were reading the room through the plants; now nothing outside `plant_care` mentions plants to ask
  what the air is doing.

- The six clients that talk to the outside world — Open-Meteo, Yasno, the transit feeds, Gemini — moved out of
  the domain into `src/infrastructure/adapters/`, along with the code that reads each vendor's payload shape.
  A vendor changing their JSON now stops at the adapter instead of reaching into the domain.
- Credentials and the private docs directory can no longer reach a release image: the build context now
  excludes `*.key`, `*.password` and `home-docs/`.

## [0.2.0] - 2026-08-27

### Added

- Сторінка рослини у браузері — гербарний аркуш з фото, ритмом поливу, мікрокліматом кімнати й тим, хто
  доглядає. Відкривається за адресою `garden.lan/p/<назва>`, зроблена для гостей і для NFC-міток на горщиках
- Кнопка «Записати полив» просто на сторінці, за паролем, щоб ніхто не натиснув її випадково
- Картотека на `garden.lan` — усі рослини як теки в шухляді, і стрілки «попередній / наступний» на кожному
  аркуші, щоб з однієї мітки можна було дійти до решти
- Знімки стали живими: торкаєшся будь-якого — він лягає на аркуш; окрема таблиця порівнює перший знімок
  з останнім засувкою
- Лупа над знімком і читання мікроклімату дотиком: ведеш пальцем по графіку — показує годину, температуру
  й вологість
- Ряд закладок угорі аркуша — усі рослини поруч, перемикаєшся між ними одним дотиком
- «Regimen» — увесь догляд, а не лише полив: період, коли востаннє, коли далі, і вказівки до кожного
  (наприклад, доза добрива)
- «Diarium» — увесь збережений запис догляду, згорнутий унизу аркуша
- Кнопки для кожного виду догляду, не лише поливу, і «Деталі» поруч — вказівки більше не тиснуться внизу
- Зібрання знімків переїхало в сам аркуш, стало більшим і відкривається на весь екран

### Changed

- Кожна рослина отримала коротку адресу з власного імені (`Тігл` → `/p/tihl`) замість номера
- Сторінка тепер підписує людину тим іменем, яке вона обрала, навіть якщо запис зроблено під старим
- Тека рослини підписана її іменем, а не однією назвою родини для всіх
- «Записати полив» тепер питає «Точно полито?» замість пароля — від випадкового дотику цього досить
- «Живлення» → «Підживлення», «Знімок» → «Фотографування»
- Порожній конверт «Fragmenta» більше не показується, а «У межах бажаного» прибрано — це й так видно на шкалі
- Оновлення на Pi тепер везе зібраний образ із номером версії, а не те, що випадково лежало в робочій теці,
  тож завжди видно, що саме там працює. Pi більше нічого не компілює
- Кожен модуль тепер сам призначає свою розкладену роботу; спільний файл розкладу перестав бути місцем,
  яке доводиться правити щоразу

### Fixed

- Помилка в будь-якому розділі більше не відповідає «не знаходжу цю рослину». Спільний текст помилки був
  узятий із розділу рослин, тож зниклий запис у покупках повідомлявся як зникла рослина

## [0.1.0]

### Added

- Telegram bot (aiogram 3) with a Ukrainian interface, restricted to an allowlist of Telegram user ids
- Guided `/add` flow: name, photo, species, location, watering interval, last watering
- Care schedules per plant — watering, fertilizing, misting, repotting, rotating — each on its own interval,
  rescheduled from the moment care actually happened
- Daily care digest at a configurable time, listing due and overdue tasks with one-tap buttons
- Care attribution — every recorded event keeps who performed it, and a guard warns before the same care is
  recorded twice within `RECENT_CARE_GUARD_HOURS`
- Photo journal per plant, stored as Telegram file ids with an optional local copy on disk
- `/plants`, `/today`, `/history` commands and plant cards with inline actions
- SQLite persistence with Alembic migrations, Unit of Work and repositories
