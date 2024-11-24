import argparse

import matplotlib.pyplot as plt
import numpy as np

def load_and_display_binary(filename, width):
    """Load and display a binary file as an image.
    
    Parameters:
        filename (str): The name of the file to read.
        width (int): The width of the image in pixels.
        
    Returns:
        None
    """
    with open(filename, 'rb') as file:
        data = file.read()

    if len(data) == 0:
        print('File is empty!')
        return None
    
    if width <= 0:
        print('Width must be greater than 0!')
        return None
    
    matrix = np.frombuffer(data, dtype=np.uint8)
    
    while matrix.size%width != 0:
        matrix = np.append(matrix, [0])

    matrix = np.reshape(matrix, (-1, width))
    print(f'matrix shape displayed : {matrix.shape}')
    
    fig, ax = plt.subplots(layout="constrained")
    ax.matshow(matrix, cmap='gist_ncar')

    #set axis off
    ax.axis('off')

    plt.show()

def main():
    parser = argparse.ArgumentParser(description='Load and display binary file')
    parser.add_argument('filename', help='the name of the binary file to load')
    parser.add_argument('-w', '--width', type=int, help='packetsize')
    args = parser.parse_args()
    
    load_and_display_binary(args.filename, args.width)

if __name__ == '__main__':
    main()