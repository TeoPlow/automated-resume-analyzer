import logging
from fastapi import FastAPI
from libs import install_exception_handlers, install_health_endpoint


app = FastAPI(title="Matching Service")
install_exception_handlers(app)
install_health_endpoint(app)
