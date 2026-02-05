"""
OpenTelemetry tracing configuration for Application Insights.
"""
import logging
from typing import Optional
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import trace

logger = logging.getLogger(__name__)


class TracingConfig:
    """Configure distributed tracing for the application."""
    
    def __init__(self, connection_string: Optional[str] = None):
        """
        Initialize tracing configuration.
        
        Args:
            connection_string: Application Insights connection string
        """
        self.connection_string = connection_string
        self.is_configured = False
    
    def configure(self, app=None):
        """
        Configure OpenTelemetry tracing with Application Insights.
        
        Args:
            app: FastAPI application instance to instrument
        """
        if not self.connection_string:
            logger.warning("Application Insights connection string not provided. Tracing disabled.")
            return
        
        try:
            # Configure Azure Monitor
            configure_azure_monitor(
                connection_string=self.connection_string,
                logger_name="ai_sales_coach"
            )
            
            # Instrument FastAPI if app provided
            if app:
                FastAPIInstrumentor.instrument_app(app)
            
            self.is_configured = True
            logger.info("OpenTelemetry tracing configured with Application Insights")
            
        except Exception as e:
            logger.error(f"Failed to configure tracing: {e}")
            logger.warning("Application will continue without tracing")
    
    def get_tracer(self, name: str = "ai_sales_coach"):
        """
        Get a tracer instance for manual instrumentation.
        
        Args:
            name: Tracer name
            
        Returns:
            Tracer instance
        """
        return trace.get_tracer(name)


def instrument_function(tracer, span_name: str):
    """
    Decorator to instrument a function with tracing.
    
    Args:
        tracer: OpenTelemetry tracer instance
        span_name: Name for the trace span
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name):
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name):
                return func(*args, **kwargs)
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
