FROM python:3.10-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . .

# Запускаем бота. 
# Укажи здесь главный файл твоего бота (например, bot.py или main.py)
CMD ["python", "main.py"]
