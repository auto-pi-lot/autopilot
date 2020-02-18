"""
I2C based thermal camera
using
https://github.com/sneakers-the-rat/mlx90640-library

"""

import numpy as np
import matplotlib
#matplotlib.use('GTKAgg')
from matplotlib import pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.axes_grid1 import make_axes_locatable

from collections import deque

import MLX90640 as cam

global current_frame
current_frame = 0

def capture_images(i=0):
	cam.setup(32)
	
	try:
		while True:
			frame = np.array(cam.get_frame()).reshape((32,24), order="F")
			yield frame
			
	except KeyboardInterrupt:
		cam.cleanup()
		
def update_plot(frame):
	global current_frame
	frames[:,:,current_frame] = frame
	#frames.append(frame)
	current_frame = (current_frame+1) % AVG_FRAMES
	
	mean_frame = np.mean(frames, axis=2)
	
	img.set_data(mean_frame)
	img.set_clim(np.min(mean_frame), np.max(mean_frame))
	return [img]
	

	
	
		
		
def main():

   
	ani = FuncAnimation(plt.gcf(), update_plot, frames=iterator, blit=False)
	
	plt.show()
    #plt.close(fig)
		

			
if __name__ == "__main__":

		
	fig = plt.figure()
	ax = fig.add_subplot(111)

	# I like to position my colorbars this way, but you don't have to
	div = make_axes_locatable(ax)
	cax = div.append_axes('right', '5%', '5%')
	
	iterator = capture_images()
		
	first_frame = next(iterator)
	img = ax.imshow(first_frame, origin='upper')
	cb = fig.colorbar(img, cax=cax)
	
	AVG_FRAMES = 5
	
	frames = np.zeros((first_frame.shape[0], first_frame.shape[1],AVG_FRAMES),
	                  dtype=first_frame.dtype)

	
	
	#frames = deque(maxlen=10)
	main()

