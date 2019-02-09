"""
Warning:
    this module is unfinished, so it is undocumented.
"""

# renders a standalone webpage with bokeh of trial data for all mice in the data folder
import sys
import os
from glob import glob
import argparse
from bokeh.plotting import figure
from bokeh.io import show
from bokeh.models import ColumnDataSource
from bokeh.layouts import gridplot
from tqdm import tqdm
from rpilot.core import mouse
import colorcet as cc
import numpy as np

def load_mouse_data(data_dir):
    """
    Args:
        data_dir:
    """
    mouse_fn = [fn for fn in os.listdir(data_dir) if fn.endswith('.h5')]
    for mouse_name in tqdm(mouse_fn):
        mouse_name = os.path.splitext(mouse_name)[0]
        amus = mouse.Mouse(mouse_name, dir=data_dir)

        # get trial data - corrects, targets, etc.
        step_data = amus.get_trial_data()
        step_data['mouse'] = mouse_name
        try:
            all_mice_steps = all_mice_steps.append(step_data)
        except NameError:
            all_mice_steps = step_data

        try:
            # get historical graduation data
            grad_data = amus.get_step_history()
            grad_data['mouse'] = mouse_name
            try:
                all_mice_grad = all_mice_grad.append(grad_data)
            except NameError:
                all_mice_grad = grad_data
        except:
            pass

    return all_mice_steps, all_mice_grad

def trial_viewer(step_data, grad_data):
    """
    Args:
        step_data:
        grad_data:
    """
    step_data.loc[step_data['response'] == 'L','response'] = 0
    step_data.loc[step_data['response'] == 'R','response'] = 1
    step_data.loc[step_data['target'] == 'L','target'] = 0
    step_data.loc[step_data['target'] == 'R','target'] = 1

    palette = [cc.rainbow[i] for i in range(len(step_data['mouse'].unique()))]
    palette = [cc.rainbow[i*15] for i in range(5)]

    mice = sorted(step_data['mouse'].unique())
    current_step = step_data.groupby('mouse').last().reset_index()
    current_step = current_step[['mouse','step']]

    plots = []
    p = figure(x_range=step_data['mouse'].unique(),title='Mouse Steps',
               plot_height=200)
    p.xaxis.major_label_orientation = np.pi / 2
    p.vbar(x=current_step['mouse'], top=current_step['step'], width=0.9)
    plots.append(p)
    for i, (mus, group) in enumerate(step_data.groupby('mouse')):
        meancx = group['correct'].ewm(span=100,ignore_na=True).mean()
        p = figure(plot_height=100,y_range=(0,1),title=mus)

        p.line(group['trial_num'], meancx, color=palette[group['step'].iloc[0]-1])
        plots.append(p)
    grid = gridplot(plots, ncols=1)
    show(grid)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Visualize Trial Data")
    parser.add_argument('-d', '--dir', help="Data directory")
    args = parser.parse_args()

    if not args.dir:
        data_dir = '/usr/rpilot/data'

        if not os.path.exists(data_dir):
            raise Exception("No directory file passed, and default location doesn't exist")

        raise Warning('No directory passed, loading from default location. Should pass explicitly with -d')
    else:
        data_dir = args.dir

    # load mouse data
    print('loading mouse data...')
    step_data, grad_data = load_mouse_data(data_dir)

    print('opening plot')








