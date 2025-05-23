PROMPT_DICT = {
    'ToTex':   """Please divide the <text> according to logic and content and output it in LaTeX format layout, without losing any content.<text>:{}""",
    'ToQA':    """1, please create some <question> closely consistent with the provided <text>. Make sure that <question> is expressed in English and does not explicitly cite the text. You can include a specific scenario or context in <question>, but make sure that <text> can be used as a comprehensive and accurate answer to the question.\n2. Then, your task is to answer the user's <question> directly in English. In forming your response, you must use references to the <text> thoughtfully, ensuring that <answer> comes from text and do not add other unnecessary content. And make sure the <question> and <answer> is relative to 'domain'. Please be careful to avoid including anything that may raise ethical issues.\n3. Output standard json format {{"question":<question>, "answer":<answer>}}<text>:{}""",
    'EXPLICIT': """Please determine whether the given question <question> contains a specific entity, or involves a definite concept or field, or provides sufficient context to identify a specific issue. Based on the following two conditions, provide <reply>: If the question is specific and clear, or involves a definite group or concept, <reply> should be 1; if the question is vague and lacks specific entities or concepts, <reply> should be 0.
                <question>: {}
                <reply>:""",
    'RELATIVE': """Please determine whether the given question <question> is relative to the 'domain'. Based on the following two conditions, provide <reply>: If it is likely, <reply> should be 1; if it is unlikely, <reply> should be 0.
                <question>: {}
                <reply>:""",
    'MORE_QA': """Please generate more questions and answers based on the provided <text>. Ensure that the generated questions are diverse and cover various aspects of the content. The generated questions should be in English and not explicitly cite the text. You can include a specific scenario or context in the questions, but make sure that the <text> can be used as a comprehensive and accurate answer to the question.
                <text>: {}
                <questions>:""",
    'GENERATE_PROMPT': """Please generate a set of prompt words for generating question answer pairs based on the domain description {} of the text data entered by the user. These prompt words will be used to guide the large model in generating question and answer pairs related to the field""",
}
