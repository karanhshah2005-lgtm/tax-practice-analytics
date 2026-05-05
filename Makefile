.PHONY: build clean serve deploy help

help:
	@echo "Tax Practice Analytics — Make targets"
	@echo "  make build    Generate database, run queries, build dashboard"
	@echo "  make serve    Serve dashboard on http://localhost:8000"
	@echo "  make clean    Remove generated files"
	@echo "  make deploy   Build and remind you to push"

build:
	python3 generate_data.py
	python3 run_analysis.py
	@echo ""
	@echo "✓ Build complete. Open index.html in a browser."

serve: build
	@echo "→ Serving on http://localhost:8000"
	@python3 -m http.server 8000

clean:
	rm -f tax_practice.db results.json dashboard.html index.html
	rm -rf __pycache__

deploy: build
	@echo ""
	@echo "→ Build complete. Now push to GitHub:"
	@echo "    git add -A && git commit -m 'rebuild dashboard' && git push"
	@echo "  GitHub Pages will redeploy automatically."
