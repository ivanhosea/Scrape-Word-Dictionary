from bs4 import BeautifulSoup as bs
import multiprocessing as mp
import httpx
import requests
import re
import concurrent.futures as cf
import time
import asyncio
import aiofiles
from string import ascii_lowercase

NUM_PROCESS = 4
NUM_THREAD = 4
NUM_BATCH_STRING = 250

BATCH_STRING = [None for i in range(NUM_BATCH_STRING)]
ALLOWED_WORD_TYPES = ('noun', 'verb', 'adjective', 'adverb', 'preposition', 'conjunction')
ROOT_URL = 'https://dictionary.cambridge.org'
HEADERS = requests.utils.default_headers()
HEADERS.update({'User-Agent': 'UserAgent1'})
ERRS = []

# Word pattern of only alphabet
WORD_PATTERN = r'^[a-zA-Z]+$'

async def main():
    # Initiate root connection
    root_session = httpx.Client()

    # Initiate queues for communication between processes
    input_queue = mp.Queue(maxsize=1)
    output_queue = mp.Queue(maxsize=5)
    
    # Initiates worker processes
    procs = []
    for i in range(NUM_PROCESS):
        procs.append(mp.Process(target=workerProcess, args=(input_queue, output_queue, i)))
        procs[i].start()
    
    write_coroutine = None

    # Write dictionary to disk asynchronously
    async with aiofiles.open('dictionary.txt', mode='w') as file_handler:
        for alpha in ascii_lowercase:
            # Get HTML page of letter A, then B, ..., Z
            web_page_alpha = fetchUrl(ROOT_URL + '/browse/english/' + alpha + '/', root_session)
            if web_page_alpha:
                batch_string_id = 0
                returned_batches = 0

                web_page_alpha = bs(web_page_alpha, 'html.parser')

                # Finding all links that each points to a page that has links to several words
                words_links = web_page_alpha.findAll(class_='hlh32 hdb dil tcbd')
                for words_link in words_links:
                    # Queue every single link to be able to multiprocess it
                    input_queue.put(str(batch_string_id) + '|' + words_link['href'])
                    batch_string_id += 1
                    
                    # Count every multiprocessing job that is finished
                    while not output_queue.empty():
                        returned_batches += getOutput(output_queue)
                
                # Wait until all jobs on this alphabet page are finished
                while returned_batches < batch_string_id:
                    returned_batches += getOutput(output_queue)
                
                # Wait until last disk write is finished, then write the next batch of words
                if write_coroutine is not None:
                    await write_coroutine
                write_coroutine = file_handler.write(''.join(BATCH_STRING[:batch_string_id]))
            
            # Error handling
            else:
                ERRS.append(ROOT_URL + '/browse/english/' + alpha + '/' + '\n')
        
        # Wait until last disk write on the loop is finished
        if write_coroutine is not None:
            await write_coroutine
    
    # Wait until all jobs are finished
    for i in range(NUM_PROCESS):
        input_queue.put('exit')
    while any(proc.is_alive() for proc in procs):
        print('still alive...')
        time.sleep(1)
    
    # Print error messages
    print('ERRORS:', len(ERRS))
    for err in ERRS:
        print(err)

    print('finished.')

# The worker processes main function
def workerProcess(input_queue, output_queue, w_id):
    # Initiate connections
    sessions = [httpx.Client() for i in range(NUM_THREAD)]

    words_error_chunks_threads = [None for i in range(NUM_THREAD)]
    
    # Initiate threads
    with cf.ThreadPoolExecutor(max_workers=NUM_THREAD) as executor:
        # The worker process will be alive until the queue inputs 'exit'
        while True:
            input_ = input_queue.get()
            print('W' + str(w_id), 'DO:', input_)
            if input_ == 'exit':
                break

            words = ''
            error = ''

            # Gets & parses input from queue
            batch_string_id, words_link_href = input_.split('|')

            # Get HTML page that contains several words
            words_page = fetchUrl(words_link_href, sessions[0])
            if words_page:
                # Parse the HTML page then get a list of every link that points to the actual word page 
                words_page = bs(words_page, 'html.parser')
                word_links = words_page.select('.hlh32.han > a')

                # Handle each word page link in a thread
                words_error_chunks = deployThreads(word_links, sessions, executor, words_error_chunks_threads)

                # Add every found word & error
                for w, e in words_error_chunks:
                    words += w
                    error += e
            else:
                error += (words_link_href + '\n')
            
            # Return the output to the main process through an output queue
            output_queue.put(batch_string_id + '|' + words + '|' + error)
    return

# Deploy the thread
def deployThreads(word_links, sessions, executor, words_error_chunks_threads):
    # Calculate the base number of links each thread will handle
    num_word_links = len(word_links)
    thread_chunk = num_word_links // NUM_THREAD
    thread_remainder = num_word_links % NUM_THREAD

    start_chunk_id = 0
    for i in range(NUM_THREAD):
        # Select the subset of the word links to be deployed in following thread
        if thread_remainder > 0:
            end_chunk_id = start_chunk_id + thread_chunk + 1
            thread_remainder -= 1
        else:
            end_chunk_id = start_chunk_id + thread_chunk
        
        # Start the thread job
        words_error_chunks_threads[i] = executor.submit(getWordsChunkThread, word_links[start_chunk_id:end_chunk_id], sessions[i])

        start_chunk_id = end_chunk_id
    
    # Wait until all threads finished, then return each of the result
    cf.wait(words_error_chunks_threads, return_when=cf.ALL_COMPLETED)
    return [t.result() for t in words_error_chunks_threads]

# The thread function
def getWordsChunkThread(word_links_chunk, session):
    words_chunk = ''
    error_chunk = ''
    for word_link in word_links_chunk:
        the_word = word_link.text.strip()

        # Fetch page of the link if the word only contains alphabets
        if bool(re.match(WORD_PATTERN, the_word)):
            # Get actual word HTML page
            word_page = fetchUrl(ROOT_URL + word_link['href'], session)
            if word_page:
                # Find the word types of the word
                word_types = bs(word_page, 'html.parser')
                word_types = word_types.select('.posgram.dpos-g.hdib.lmr-5 > .pos.dpos')

                # If at least 1 of the word type exists in the ALLOWED_WORD_TYPES, the word is added to the list
                for word_type in word_types:
                    if word_type.text in ALLOWED_WORD_TYPES:
                        words_chunk += (the_word + '\n')
                        break
            else:
                error_chunk += (ROOT_URL + word_link['href'] + '\n')
    return words_chunk, error_chunk

# Getting the output from the output queue to the main process
def getOutput(output_queue):
    # Get & Parse the output
    batch_string_id, response, error = output_queue.get().split('|')

    # Place the words in the batch string
    BATCH_STRING[int(batch_string_id)] = response

    if error != '':
        ERRS.append(error)
    return 1

# Perform HTTP request using a given HTTP connection
def fetchUrl(url, session):
    try:
        response = session.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response.text
        return None
    except:
        return None

if __name__ == '__main__':
    asyncio.run(main())