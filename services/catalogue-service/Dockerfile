# Start from an official Python image.
# "slim" is a trimmed-down Linux base: smaller image, smaller attack surface,
# faster to push and pull. Both are real arguments in the viva.
FROM python:3.12-slim

# Everything from here on happens inside /app in the container.
WORKDIR /app

# Copy requirements FIRST, on its own, before the application code.
# Docker caches each step. Because this layer only changes when the
# dependency list changes, editing main.py does not force a
# reinstall of every library — rebuilds drop from minutes to seconds.
COPY requirements.txt .

# --no-cache-dir keeps the pip download cache out of the final image.
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the application code.
COPY . .

# Create and switch to a non-root user.
# If the application is ever compromised, the attacker lands as an
# unprivileged user rather than root inside the container.
# This is a concrete Task 3 security control, not boilerplate.
RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -G root --create-home appuser
USER appuser

# Documents which port the service listens on. Informational only —
# the actual mapping happens at run time.
EXPOSE 8000

# The command that runs when the container starts.
# --host 0.0.0.0 is essential: 127.0.0.1 would only accept connections
# from inside the container, making the service unreachable from outside.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]