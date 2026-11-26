FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.0 uvicorn==0.30.6
COPY apps/mocks/common.py /app/common.py
COPY apps/mocks/m365_sim/ /app/m365_sim/
EXPOSE 9105
CMD ["uvicorn", "m365_sim.main:app", "--host", "0.0.0.0", "--port", "9105"]
