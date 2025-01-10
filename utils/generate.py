from model_api.prompts import PROMPT_DICT
from model_api.erine.erine import generate_erine
from model_api.flash.flash import generate_flash
from model_api.lite.lite import generate_lite
from model_api.Qwen.Qwen import generate_Qwen

def generate(text, Model_Name,  prompt_choice, API_KEY, SECRET_KEY=None):

    Model_Name.lower()

    if Model_Name == "erine":
        generate_erine(text, API_KEY, SECRET_KEY, prompt_choice)
    elif Model_Name == "flash":
        generate_flash(text, API_KEY, prompt_choice)
    elif Model_Name == "lite":
        generate_lite(text, API_KEY, prompt_choice)
    elif Model_Name == "qwen":
        generate_Qwen(text, API_KEY, prompt_choice)
    else:
        print("您输入的模型名字有误！请重新输入。")