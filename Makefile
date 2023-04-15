EXCALIDRAW_VERSION ?= master

## Meta installation targets
build: apps build-apps
apps: clone-external-repos excalidraw-checkout

clone-external-repos:
	mkdir -p external-repos
	@git clone https://github.com/b310-digital/excalidraw.git external-repos/excalidraw || echo "Already installed"
	cp .env external-repos/excalidraw

checkout-version:
	cd external-repos/$(APP_FOLDER); git fetch; git checkout $(APP_VERSION); cp ../../.env .

excalidraw-checkout:
	make checkout-version -e APP_FOLDER=excalidraw -e APP_VERSION=$(EXCALIDRAW_VERSION)

build-apps:
	docker compose build
