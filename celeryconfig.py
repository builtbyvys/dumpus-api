import os

broker_url=os.getenv('REDIS_URL')
task_ignore_result=True
task_acks_late=True
