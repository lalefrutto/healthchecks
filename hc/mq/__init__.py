"""Producer/Consumer поверх RabbitMQ на прямом AMQP-клиенте (pika), без Celery.

Задание 3, Часть 2. Модуль намеренно не зависит от Django — producer и
consumer запускаются как обычные скрипты и снаружи кластера (через
LoadBalancer-сервис RabbitMQ), и внутри него.

    python -m hc.mq.producer cat_fact
    python -m hc.mq.producer weather --latitude 55.79 --longitude 49.11
    python -m hc.mq.consumer api-results

Адрес брокера берётся из переменной окружения RABBITMQ_URL
(amqp://user:password@host:5672/%2F).
"""
