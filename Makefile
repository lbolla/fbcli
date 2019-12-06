.EXPORT_ALL_VARIABLES:
.PHONY: help

# Self-documenting Makefile
# https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
help:  ## Print this help
	@grep -E '^[a-zA-Z][a-zA-Z0-9_-]*:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

clean-repo:
	git diff --quiet HEAD  # no pending commits
	git diff --cached --quiet HEAD  # no unstaged changes
	git pull --ff-only  # latest code

release: clean-repo  ## Make a release (specify: PART=[major|minor|patch])
	pip install -U bump2version
	bump2version ${PART}
	git push
	git push --tags
