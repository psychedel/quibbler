# Quibbler
**Interactive, reproducible and efficient data analytics**

![GitHub](https://img.shields.io/github/license/Technion-Kishony-lab/quibbler)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/Technion-Kishony-lab/quibbler)

https://user-images.githubusercontent.com/62783755/209929327-67766771-f271-40f0-8f3a-76deb88310b7.mp4

## What is it?
<img src="https://github.com/Technion-Kishony-lab/quibbler/blob/master/pyquibbler-documentations/docs/images/quibicon.gif?raw=true" width=250 align='right'>

*Quibbler* is a toolset for building highly interactive, yet reproducible, 
transparent and efficient data analysis pipelines. *Quibbler* allows using standard 
*Python* syntax to process data through any series of analysis steps, while 
automatically maintaining connectivity between downstream results and upstream raw data 
sources. *Quibbler* facilitates and embraces human interventions as an inherent part 
of the analysis pipeline: input parameters, as well as exceptions and overrides, 
can be specified and adjusted either programmatically, or by 
interacting with "live" graphics, and all such interventions are automatically 
recorded in well-documented human-machine readable files. Changes to such parameters 
propagate downstream, pinpointing which specific data items, or
even specific elements thereof, are affected, thereby vastly saving unnecessary 
recalculations. *Quibbler*, therefore, facilitates hands-on interactions with data 
in ways that are not only flexible, fun and interactive, but also traceable, 
reproducible, and computationally efficient.


### Check out our "Best Quibble" competition!
We just launched *Quibbler* in [PyData Tel-Aviv](https://pydata.org/telaviv2022/).
We are seeking engagement from users and developers and are also eager to learn of 
the range of applications for *Quibbler*. 
To get it fun and going, we are announcing a competition for the best **"Quibble"** - 
a short elegant quib-based code that demonstrates fun interactive graphics and/or hints 
to ideas of applications. 

The competition is open to everyone. 
For details (and prizes!) see: [Best Quibble Award](https://kishony.technion.ac.il/best-quibble-award/)   


## Main Features

* **Interactivity** 

  * Creating [interactive graphics](https://quibbler.readthedocs.io/en/latest/Quickstart.html) is as 
simple as calling standard Matplotlib graphics functions with arguments that represent your parameter values.

  * Any data presented graphically is automatically live and interactive 
(no need for the tedious programming of callback functions).

* **Traceability and Reproducibility**
  * Trace which specific data items and analysis parameters affect focal downstream results (see 
[dependency graph](https://quibbler.readthedocs.io/en/latest/Quib-relationships.html)).  

  * Inherent [undo/redo](https://quibbler.readthedocs.io/en/latest/Jupyter-lab-ext.html) functionality.

  * [Save/load](https://quibbler.readthedocs.io/en/latest/Project-save-load.html) parameter values as 
human-readable records (either as external text files, 
or [inside Jupyter notebook](https://quibbler.readthedocs.io/en/latest/Jupyter-lab-ext.html)).

* **Computational efficiency**
  * Upon parameter changes, *Quibbler* pinpoints and only recalculates the specifically affected array elements 
of downstream analysis steps ([here](https://quibbler.readthedocs.io/en/latest/Diverged-evaluation.html)).

* **Very little to learn: your standard-syntax code automatically comes to life.**
  * To get started with Quibbler, you do not need to learn any new syntax or new functions. Just encapsulate your
input parameters with `iquib` and your analysis and graphics automatically become live and interactive. 
  * Quibbler supports standard coding syntax with all Python operators, slicing, getitem, Numpy functions, 
Matplotlib graphics functions, Matplotlib widgets, and ipywidgets. It further provides an easy way to incorporate 
any user functions or functions from any other non-graphics packages ([here](https://quibbler.readthedocs.io/en/latest/User-defined-functions.html)). 
Support for other graphics packages, besides Matplotlib, will be offered in future releases.       

## Minimal app
```python
from pyquibbler import initialize_quibbler, iquib
initialize_quibbler()
import matplotlib.pyplot as plt

x = iquib(0.5)
y = 1 - x
plt.plot([0, 1], [1, 0], '-')
plt.plot([0, x, x], [y, y, 0], '--', marker='D')
plt.title(x, fontsize=20)
```

![](https://github.com/Technion-Kishony-lab/quibbler/blob/master/pyquibbler-documentations/docs/images/minimal_app_3.gif?raw=true)


## Documentation and Examples
For complete documentation and a getting-started tour, see [readthedocs](https://quibbler.readthedocs.io/en/latest/). 

For simple demos and small apps, see our [Examples](https://quibbler.readthedocs.io/en/latest/Examples.html).  

## Installation 

We recommend installing *Quibbler* in a new virtual environment 
(see [creating a new environment](https://github.com/Technion-Kishony-lab/quibbler/blob/master/INSTALL.md)). 

To install run:

`pip install pyquibbler`

If you are using Quibbler within *Jupyter lab*, you can also add the 
[pyquibbler Jupyter Lab extension](https://quibbler.readthedocs.io/en/latest/Jupyter-lab-ext.html):

`pip install pyquibbler_labextension`

## Development 
To install for developers, 
see our guide [here](https://github.com/Technion-Kishony-lab/quibbler/blob/master/INSTALL.md).

## Credit

Quibbler was created by Roy Kishony, initially implemented as a Matlab toolbox. 

The first release of Quibbler for Python, *pyquibbler*, was developed at the 
[Kishony lab](https://kishony.technion.ac.il/quibbler/), 
[Technion - Israel Institute of Technology](https://www.technion.ac.il/), 
by Maor Kern, Maor Kleinberger and Roy Kishony.

We very much welcome any thoughts, suggestions and ideas and of course welcome PR contributions 
(for some proposed directions, see our pending [issues](https://github.com/Technion-Kishony-lab/quibbler/issues)). 

## Related packages

* [Matplotlib](https://github.com/matplotlib/matplotlib)
* [Streamlit](https://streamlit.io/)
* [Plotly](https://plotly.com/)
* [Shiny](https://shiny.rstudio.com/)
* [ipywidgets](https://github.com/jupyter-widgets/ipywidgets)
* [bokeh](http://bokeh.org)
* [HoloViz](https://holoviz.org/)
* [Vega-Altair](https://altair-viz.github.io/)
* [Datashader](https://datashader.org/)
