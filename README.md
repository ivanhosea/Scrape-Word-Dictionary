# Scrape-Word-Dictionary
Web Scraping from the website https://dictionary.cambridge.org/ to get word dictionary using Selenium & BeautifulSoup.
## Requirements
- Selenium
- BeautifulSoup
- httpx
- asyncio
- aiofiles
## Getting Started
1. Install Python 3
2. Install the requirements:
    ```
    pip install Selenium beautifulsoup4 httpx asyncio aiofiles
    ```
3. To scrape the web, run:
    ```
    python scrape_dictionary_multiprocessing.py
    ```
## Implementation
- Selenium is used because the webpage is dynamic, which means an HTTP request to get the webpage will return the script for generating the web instead of the actual data that is needed.
- Multiprocessing is used to make computation faster.
- Multithreading on each process is implemented to utilize the I/O wait for computation in other thread instead.
- Multiple HTTP connections are created on each process to make sure each thread in the process can have its own HTTP connection. Each worker process is kept alive as long as the program is running so that the program doesn't need to redeploy the process and recreate the threads and HTTP connections.
- The word must belong to at least one of these categories: noun, verb, adjective, adverb, preposition, conjunction.
- Multiprocessing Queues are used for communication between processes.
## Result
Dictionary with 53K words.