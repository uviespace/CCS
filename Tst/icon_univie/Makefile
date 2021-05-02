BUILD_DIR = $(CURDIR)/generated

.PHONY: build clean-build

all: clean-build build
clean: clean-build

build:
	@echo "\e[1m=====================================\e[0m"
	@echo "\e[1m Generating SVGs \e[0m"
	@echo "\e[1m=====================================\e[0m"
		python3 create_univie_icons.py
	@echo "\e[1m\e[32m==================================\e[0m"
	@echo "\e[1m\e[32m Successful generated SVGs \e[0m"
	@echo "\e[1m\e[32m==================================\e[0m"
	@echo

clean-build:
	@echo "\e[1m=============================================================\e[0m"
	@echo "\e[1m deleting all generated SVGs \e[0m"
	@echo "\e[1m=============================================================\e[0m"
	@echo $(BUILD_DIR)
		rm -rf $(BUILD_DIR)
	@echo "\e[1m\e[32m============================================================\e[0m"
	@echo "\e[1m\e[32m deleted all generated SVGs \e[0m"
	@echo "\e[1m\e[32m============================================================\e[0m"
	@echo
