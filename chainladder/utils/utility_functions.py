# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import pandas as pd
import numpy as np
from scipy.sparse import coo_matrix
import joblib
import json
import os
from chainladder.core.triangle import Triangle
from chainladder.workflow import Pipeline


def load_dataset(key, *args, **kwargs):
    """ Function to load datasets included in the chainladder package.

        Arguments:
        key: str
        The name of the dataset, e.g. RAA, ABC, UKMotor, GenIns, etc.

        Returns:
    	pandas.DataFrame of the loaded dataset.

   """
    path = os.path.dirname(os.path.abspath(__file__))
    origin = 'origin'
    development = 'development'
    columns = ['values']
    index = None
    if key.lower() in ['mcl', 'usaa', 'quarterly', 'auto', 'usauto']:
        columns = ['incurred', 'paid']
    if key.lower() == 'clrd':
        origin = 'AccidentYear'
        development = 'DevelopmentYear'
        index = ['GRNAME', 'LOB']
        columns = ['IncurLoss', 'CumPaidLoss', 'BulkLoss', 'EarnedPremDIR',
                   'EarnedPremCeded', 'EarnedPremNet']
    if key.lower() in ['liab', 'auto']:
        index = ['lob']
    if key.lower() in ['cc_sample', 'ia_sample']:
        columns = ['loss', 'exposure']
    df = pd.read_csv(os.path.join(path, 'data', key.lower() + '.csv'))
    return Triangle(df, origin=origin, development=development, index=index,
                    columns=columns, cumulative=True, *args, **kwargs)


def read_pickle(path):
    return joblib.load(path)


def read_json(json_str):
    def sparse_in(json_str, dtype, shape):
        k, v, o, d = shape
        x = json.loads(json_str)
        y = np.array([tuple([int(idx) for idx in item[1:-1].split(',')])
                      for item in x.keys()])
        new = coo_matrix(
            (np.array(list(x.values())), (y[:, 0], y[:, 1])),
            shape=(k*v*o, d), dtype=dtype).toarray().reshape(k,v,o,d)
        new[new==0] = np.nan
        return new

    json_dict = json.loads(json_str)
    if type(json_dict) is list:
        import chainladder as cl
        return Pipeline(steps=[
            (item['name'],
             cl.__dict__[item['__class__']]().set_params(**item['params']))
            for item in json_dict])
    elif 'kdims' in json_dict.keys():
        tri = Triangle()
        arrays = ['kdims', 'vdims', 'odims', 'ddims']
        for array in arrays:
            setattr(tri, array, np.array(
                json_dict[array]['array'], dtype=json_dict[array]['dtype']))
        shape = (len(tri.kdims), len(tri.vdims), len(tri.odims), len(tri.ddims))
        properties = ['key_labels', 'origin_grain', 'development_grain',
                    'nan_override', 'is_cumulative']
        for prop in properties:
            setattr(tri, prop, json_dict[prop])
        tri.valuation_date = pd.to_datetime(
            json_dict['valuation_date'], format='%Y-%m-%d')
        tri._set_slicers()
        tri.valuation = tri._valuation_triangle()
        if json_dict['values'].get('sparse', None):
            tri.values = sparse_in(json_dict['values']['array'], json_dict['values']['dtype'], shape)
            if tri.is_cumulative:
                tri.is_cumulative = False
                tri = tri.incr_to_cum()
        else:
            tri.values = np.array(json_dict['values']['array'], dtype=json_dict['values']['dtype'])

        return tri
    else:
        import chainladder as cl
        return cl.__dict__[
            json_dict['__class__']]().set_params(**json_dict['params'])



def parallelogram_olf(values, date, start_date=None, end_date=None,
                      grain='M', vertical_line=False):
    """ Parallelogram approach to on-leveling.  Need to fix return grain
    """
    date = pd.to_datetime(date)
    if not start_date:
        start_date = '{}-01-01'.format(date.min().year-1)
    if not end_date:
        end_date = '{}-12-31'.format(date.max().year+1)
    date_idx = pd.date_range(start_date, end_date)
    y = pd.Series(np.array(values), np.array(date))
    y = y.reindex(date_idx, fill_value=0)
    idx = np.cumprod(y.values+1)
    idx = idx[-1]/idx
    y = pd.Series(idx, y.index)
    if not vertical_line:
        y = y.to_frame().rolling(365).mean()
    y = y.groupby(y.index.to_period(grain)).mean().reset_index()
    y.columns = ['Origin', 'OLF']
    y['Origin'] = y['Origin'].astype(str)
    return y.set_index('Origin')
