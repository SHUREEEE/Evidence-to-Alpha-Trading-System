.PHONY: demo test serve

demo:
	python -m evidence_alpha demo --output-dir artifacts/demo

test:
	python -m unittest discover -s tests -v

serve:
	python -m evidence_alpha serve --artifact-dir artifacts/demo --port 8080 --bootstrap-demo

