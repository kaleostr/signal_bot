ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip tzdata py3-numpy py3-yaml

RUN python3 -m venv /opt/venv --system-site-packages
ENV PATH="/opt/venv/bin:${PATH}"     PIP_NO_CACHE_DIR=1     PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

WORKDIR /opt/app

COPY requirements.txt /opt/requirements.txt
RUN pip install --upgrade pip && pip install -r /opt/requirements.txt

COPY src /opt/app/src
COPY run.sh /run.sh
RUN sed -i 's/\r$//' /run.sh && chmod +x /run.sh

CMD ["/run.sh"]
