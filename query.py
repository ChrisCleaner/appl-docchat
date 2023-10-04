import os
import sys
from loguru import logger
# local imports
from query.querier import Querier
import settings
import utils


def exit_program():
    print("Exiting the program...")
    sys.exit(0)


def main():
    # Create instance of Querier once
    querier = Querier(settings.EMBEDDINGS_TYPE, settings.VECDB_TYPE, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
    # Get source folder with docs from user
    content_folder_name = input("Source folder of documents (without path): ")
    # get associated vectordb path
    _, vectordb_folder_path = utils.create_vectordb_name(content_folder_name, 
                                                         settings.DOC_DIR, 
                                                         settings.VECDB_DIR, 
                                                         settings.VECDB_TYPE, 
                                                         settings.EMBEDDINGS_TYPE, 
                                                         settings.CHUNK_SIZE, 
                                                         settings.CHUNK_OVERLAP)

    # If vector store folder does not exist, stop
    if not os.path.exists(vectordb_folder_path):
        logger.info("There is no vector database for this folder yet. First run \"python ingest.py\"")
        exit_program()
    else:
        # create the query chain
        querier.make_chain(content_folder_name, vectordb_folder_path)
        while True:
            # Get question from user
            question = input("Question: ")
            if question not in ["exit", "quit", "q"]:
                # log the question
                logger.info(f"\nQuestion: {question}")
                # Generate answer and include sources used to produce that answer
                answer, source = querier.ask_question(question)
                # log the answer to the question and the sources used for creating the answer
                logger.info("\nSources:\n")
                for document in source:
                    logger.info(f"Page {document.metadata['page_number']} chunk used: {document.page_content}\n")
                logger.info(f"\nAnswer: {answer}")
            else:
                exit_program()


if __name__ == "__main__":
    main()
