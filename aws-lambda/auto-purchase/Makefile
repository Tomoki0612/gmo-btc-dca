build-BtcAutoPurchaseFunction:
	python3 -m pip install --requirement requirements.txt --target "$(ARTIFACTS_DIR)" \
		--platform manylinux2014_x86_64 --python-version 3.12 \
		--implementation cp --only-binary=:all:
	cp btc_auto_purchase.py "$(ARTIFACTS_DIR)/"
