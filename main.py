
import sys
import os
import wikipedia
import re
import aiohttp
import asyncio
from datetime import date

OPENAI_API_KEY_ENV_VAR = "OPENAI_API_KEY"
OPENAI_API_URL = "https://api.openai.com/v1/completions"

MODEL = "text-davinci-002"
TEMPERATURE = 0.7
MAX_TOKENS = 256

CONTEXT_CHAR_LIMIT = 4000
CONTEXT_HALF_SIZE = 300
EXCERPT_HALF_SIZE = 200

CONTEXT_DIVIDER = " [...] "
BOLD_SEQUENCE_START = "\033[1m"
BOLD_SEQUENCE_END = "\033[0m"

INTRO_MESSAGE = "\nWelcome to Wikipedia GPT-3 Bot. Ask any question.\n"
REPL_PROMPT = "(wikibot) "

DATE_TODAY = date.today().strftime("%B %d, %Y")


def ensure_env_vars():
    if OPENAI_API_KEY_ENV_VAR not in os.environ:
        print(f"{OPENAI_API_KEY_ENV_VAR} not found in environment variables")
        sys.exit(1)


async def gen_completion(prompt):
    params = {
        "model": MODEL,
        "prompt": prompt,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }
    headers = {"Authorization": f"Bearer {os.environ[OPENAI_API_KEY_ENV_VAR]}"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(OPENAI_API_URL, json=params) as resp:
            return sanitize_response((await resp.json())["choices"][0]["text"])


def sanitize_response(response):
    return response.strip().replace("\n", "").replace("\"", "")


async def question_to_page_search_query(question):
    prompt = f"""
Which Wikipedia page would you search for to answer the following question: "{question}"

Page name:"""

    return await gen_completion(prompt)


def page_search_query_to_page(page_search_query):
    search_results = wikipedia.search(page_search_query)

    if len(search_results) == 0:
        print("No Wikipedia pages found to answer the question")
        sys.exit(1)

    try:
        return wikipedia.page(search_results[0], auto_suggest=False)
    except wikipedia.DisambiguationError as e:
        return wikipedia.page(e.options[0], auto_suggest=False)


async def generate_ctrlf_term(page, question):
    prompt = f"""
Given the Wikipedia page for "{page.title}", what word would you search for on the page to answer the question "{question}"

Search term:"""

    return await gen_completion(prompt)


def generate_context(page, ctrlf_term):
    matches = [match.start() for match in re.finditer(
        ctrlf_term, page.content, re.IGNORECASE)]

    top_three_contexts = []
    for match in matches:
        if len(top_three_contexts) == 3:
            break

        excerpt = page.content[match - CONTEXT_HALF_SIZE: match +
                               CONTEXT_HALF_SIZE] if match > CONTEXT_HALF_SIZE else page.content[0: match + match]

        if excerpt in page.summary:
            continue

        top_three_contexts.append(excerpt.strip())

    return (CONTEXT_DIVIDER.join([page.summary.strip()] +
                                 top_three_contexts))[:CONTEXT_CHAR_LIMIT]


async def generate_answer(context, question):
    prompt = f"""
Background text: 

"{context}"

Answer the following question using only the background text above. Today's date is {DATE_TODAY}.

Question: "{question}"
Answer:"""

    return await gen_completion(prompt)


async def generate_excerpt(context, question):
    prompt = f"""
Background text: 

"{context}"

Given the background text above, which substring would you highlight to answer the question "{question}"

Excerpt:"""

    excerpt = await gen_completion(prompt)

    if excerpt in context:
        return excerpt
    else:
        return None


def generate_context_highlighted(context, excerpt):
    if excerpt is None or excerpt not in context:
        return context.replace("\n", " ")

    context_highlighted = context.replace(
        excerpt, f"{BOLD_SEQUENCE_START}{excerpt}{BOLD_SEQUENCE_END}") if excerpt else context

    match = context_highlighted.find(excerpt)
    context_highlighted_abridged = context_highlighted[match - EXCERPT_HALF_SIZE: match + len(
        excerpt) + EXCERPT_HALF_SIZE] if match > EXCERPT_HALF_SIZE else context_highlighted[0: match + len(excerpt) + EXCERPT_HALF_SIZE]
    return context_highlighted_abridged.replace("\n", " ")


async def answer_question(question):
    page_search_query = await question_to_page_search_query(question)

    page = page_search_query_to_page(page_search_query)
    print(f"Pulling up page: {page.title}")

    ctrlf_term = await generate_ctrlf_term(page, question)

    context = generate_context(page, ctrlf_term)

    answer, excerpt = await asyncio.gather(
        generate_answer(context, question),
        generate_excerpt(context, question),
    )

    context_highlighted = generate_context_highlighted(context, excerpt)

    summary_pretty = f"""

    Answer: {BOLD_SEQUENCE_START}{answer}{BOLD_SEQUENCE_END}

    Context:

    > [...] {context_highlighted}  [...]

    URL: {page.url}

    """

    print(summary_pretty)


async def main():
    if len(sys.argv) > 1:
        await answer_question(sys.argv[1])
    else:
        print(INTRO_MESSAGE)
        while True:
            question = input(REPL_PROMPT)
            await answer_question(question)


if __name__ == '__main__':
    ensure_env_vars()
    asyncio.run(main())
