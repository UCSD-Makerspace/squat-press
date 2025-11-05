import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

pd.read_csv('test_sensor_log.csv')

df['dP'] = np.diff(df['position_mm'], prepend=np.nan)
df['dt'] = np.diff(df['time_s'], prepend=np.nan)