PROMPT_DICT = {
    'ToTex':   """Please divide the <text> according to logic and content and output it in LaTeX format layout, without losing any content.<text>:{}""",
    'ToQA':    """1, please create some <question> closely consistent with the provided <text>. Make sure that <question> is expressed in Chinese and does not explicitly cite the text. You can include a specific scenario or context in <question>, but make sure that <text> can be used as a comprehensive and accurate answer to the question.\n2. Then, you play the role of a doctor, who has in-depth knowledge in medicine. Your task is to answer the user's <question> directly in Chinese. In forming your response, you must use references to the <text> thoughtfully, ensuring that <answer> comes from text and do not add other unnecessary content. Please be careful to avoid including anything that may raise ethical issues.\n3. Output standard json format {{"question":<question>, "answer":<answer>}}<text>:{}""",
    'EXPLICIT': """Please determine whether the given question <question> contains a specific entity, or involves a definite concept or field, or provides sufficient context to identify a specific issue. Based on the following two conditions, provide <reply>: If the question is specific and clear, or involves a definite group or concept, <reply> should be 1; if the question is vague and lacks specific entities or concepts, <reply> should be 0.
                <question>: {}
                <reply>:""",
    'MEDICAL': """Please determine whether the given question <question> is likely to appear in a clinical setting. Based on the following two conditions, provide <reply>: If it is likely, <reply> should be 1; if it is unlikely, <reply> should be 0.
                <question>: {}
                <reply>:""",
    'MORE_QA': """Please generate more questions and answers based on the provided <text>. Ensure that the generated questions are diverse and cover various aspects of the content. The generated questions should be in Chinese and not explicitly cite the text. You can include a specific scenario or context in the questions, but make sure that the <text> can be used as a comprehensive and accurate answer to the question.
                <text>: {}
                <questions>:""",
}
