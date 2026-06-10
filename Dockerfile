FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir streamlit pandas

COPY . .

RUN python3 generate_sample_data.py

EXPOSE 8080

CMD ["streamlit", "run", "web/app.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]
