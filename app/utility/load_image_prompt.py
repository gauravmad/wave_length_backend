def load_image_prompt(filepath="app/syste_prompt/image_analyzer.md") -> list[str]:
    try:
        with open(filepath,"r", encoding="utf-8") as f:
            prompts = [line.strip() for line in f if line.strip()]
        return prompts

    except Exception as e:
        print(f"Failed to load image prompts:{e}")
        return ["Please analyze this image and share your thoughts"]    