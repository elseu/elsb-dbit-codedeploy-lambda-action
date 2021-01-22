FROM python:3.8-alpine

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./deploy.py" ]