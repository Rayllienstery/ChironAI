# DockerManager

Core module for Docker CLI inspection and simple lifecycle actions used by the
CoreUI Docker tab.

It intentionally depends on the Docker CLI instead of the Docker Python SDK so
it can work with the same Docker Desktop/Engine setup already used by the repo.
