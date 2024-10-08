from uuid import uuid4

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class OrderFlowChart:
    def __init__(self, orderflow_data, ohlc_data, identifier_col=None, imbalance_col=None):
        self.orderflow_data = orderflow_data
        self.ohlc_data = ohlc_data
        self.identifier_col = identifier_col
        self.imbalance_col = imbalance_col
        self.is_processed = False
        self.granularity = abs(self.orderflow_data.iloc[0]['price'] - self.orderflow_data.iloc[1]['price'])

    def create_identifier(self):
        identifier = [uuid4() for _ in range(self.ohlc_data.shape[0])]
        self.ohlc_data['identifier'] = identifier
        self.orderflow_data.loc[:, 'identifier'] = self.ohlc_data['identifier']

    def create_sequence(self):
        self.ohlc_data['sequence'] = self.ohlc_data[self.identifier_col].str.len()
        self.orderflow_data['sequence'] = self.orderflow_data[self.identifier_col].str.len()

    def calc_imbalance(self, df):
        df['sum'] = df['bid_size'] + df['ask_size']
        df['time'] = df.index.astype(str)
        bids, asks = [], []
        for b, a in zip(df['bid_size'].astype(int).astype(str),
                        df['ask_size'].astype(int).astype(str)):
            dif = 4 - len(a)
            a = a + (' ' * dif)
            dif = 4 - len(b)
            b = (' ' * dif) + b
            bids.append(b)
            asks.append(a)

        df['text'] = pd.Series(bids, index=df.index) + '  ' + pd.Series(asks, index=df.index)
        df.index = df['identifier']

        if self.imbalance_col is None:
            print("Calculating imbalance, as no imbalance column was provided.")
            df['size'] = (df['bid_size'] - df['ask_size'].shift().bfill()) / \
                         (df['bid_size'] + df['ask_size'].shift().bfill())
            df['size'] = df['size'].ffill().bfill()
        else:
            print("Using imbalance column: {}".format(self.imbalance_col))
            df['size'] = df[self.imbalance_col]
            df = df.drop([self.imbalance_col], axis=1)
        return df

    def annotate(self, df2):
        df2 = df2.drop(['size'], axis=1)
        df2['sum'] = df2['sum'] / df2.groupby(df2.index)['sum'].transform('max')
        df2['text'] = ''
        df2['time'] = df2['time'].astype(str)
        df2['text'] = ['█' * int(sum_ * 10) for sum_ in df2['sum']]
        df2['text'] = '                    ' + df2['text']
        df2['time'] = df2['time'].astype(str)
        return df2

    def range_proc(self, ohlc, type_='hl'):
        if type_ == 'hl':
            seq = pd.concat([ohlc['low'], ohlc['high']])
        if type_ == 'oc':
            seq = pd.concat([ohlc['open'], ohlc['close']])
        id_seq = pd.concat([ohlc['identifier'], ohlc['identifier']])
        seq_hl = pd.concat([ohlc['sequence'], ohlc['sequence']])
        seq = pd.DataFrame(seq, columns=['price'])
        seq['identifier'] = id_seq
        seq['sequence'] = seq_hl
        seq['time'] = seq.index
        seq = seq.sort_index()
        seq = seq.set_index('identifier')
        return seq

    def candle_proc(self, df):
        df = df.sort_values(by=['time', 'sequence', 'price'])
        df = df.reset_index()
        df_dp = df.iloc[1::2].copy()
        df = pd.concat([df, df_dp])
        df = df.sort_index()
        df = df.set_index('identifier')
        df = df.sort_values(by=['time', 'sequence'])
        df[2::3] = np.nan
        return df

    def calc_params(self, of, ohlc):
        delta = of.groupby(of['identifier']).sum()['ask_size'] - \
                of.groupby(of['identifier']).sum()['bid_size']
        delta = delta[ohlc['identifier']]
        cum_delta = delta.rolling(10).sum()
        roc = cum_delta.diff() / cum_delta.shift(1) * 100
        roc = roc.fillna(0).round(2)
        volume = of.groupby(of['identifier']).sum()['ask_size'] + of.groupby(of['identifier']).sum()['bid_size']
        delta = pd.DataFrame(delta, columns=['value'])
        delta['type'] = 'delta'
        cum_delta = pd.DataFrame(cum_delta, columns=['value'])
        cum_delta['type'] = 'cum_delta'
        roc = pd.DataFrame(roc, columns=['value'])
        roc['type'] = 'roc'
        volume = pd.DataFrame(volume, columns=['value'])
        volume['type'] = 'volume'

        labels = pd.concat([delta, cum_delta, roc, volume])
        labels = labels.sort_index()
        labels['text'] = labels['value'].astype(str)

        labels['value'] = np.tanh(labels['value'])
        return labels

    def plot_ranges(self, ohlc):
        ymin = ohlc['high'][-1] + 1
        ymax = ymin - int(48 * self.granularity)
        xmax = ohlc.shape[0]
        xmin = xmax - 9
        tickvals = [i for i in ohlc['identifier']]
        ticktext = [i for i in ohlc.index]
        return ymin, ymax, xmin, xmax, tickvals, ticktext

    def process_data(self):
        if self.identifier_col is None:
            self.identifier_col = 'identifier'
            self.create_identifier()

        self.create_sequence()

        self.df = self.calc_imbalance(self.orderflow_data)

        self.df2 = self.annotate(self.df.copy())

        self.green_id = self.ohlc_data.loc[self.ohlc_data['close'] >= self.ohlc_data['open']]['identifier']
        self.red_id = self.ohlc_data.loc[self.ohlc_data['close'] < self.ohlc_data['open']]['identifier']

        self.high_low = self.range_proc(self.ohlc_data, type_='hl')
        self.green_hl = self.high_low.loc[self.green_id]
        self.green_hl = self.candle_proc(self.green_hl)

        self.red_hl = self.high_low.loc[self.red_id]
        self.red_hl = self.candle_proc(self.red_hl)

        self.open_close = self.range_proc(self.ohlc_data, type_='oc')

        self.green_oc = self.open_close.loc[self.green_id]
        self.green_oc = self.candle_proc(self.green_oc)

        self.red_oc = self.open_close.loc[self.red_id]
        self.red_oc = self.candle_proc(self.red_oc)

        self.labels = self.calc_params(self.orderflow_data, self.ohlc_data)

        self.is_processed = True

    def get_processed_data(self):
        if not self.is_processed:
            try:
                self.process_data()
            except:
                raise Exception("Data processing failed.")

        datas = [self.df, self.labels, self.green_hl, self.red_hl, self.green_oc, self.red_oc, self.df2, self.ohlc_data]
        datas2 = []
        temp = ''
        for data in datas:
            temp = data.copy()
            temp.index.name = 'index'
            try:
                temp = temp.reset_index()
            except:
                pass
            dtype_dict = {i: str(j) for i, j in temp.dtypes.items()}
            temp = temp.astype('str')
            temp = temp.fillna('nan')
            temp = temp.to_dict(orient='list')
            temp['dtypes'] = dtype_dict
            datas2.append(temp)

        out_dict = {
            'orderflow': datas2[0],
            'labels': datas2[1],
            'green_hl': datas2[2],
            'red_hl': datas2[3],
            'green_oc': datas2[4],
            'red_oc': datas2[5],
            'orderflow2': datas2[6],
            'ohlc': datas2[7]
        }

        return out_dict

    def plot(self):
        if not self.is_processed:
            try:
                self.process_data()
            except:
                raise Exception("Data processing failed.")

        ymin, ymax, xmin, xmax, tickvals, ticktext = self.plot_ranges(self.ohlc_data)

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.0, row_heights=[9, 1])

        fig.add_trace(go.Scatter(x=self.df2['identifier'], y=self.df2['price'], text=self.df2['text'],
                                 name='VolumeProfile', textposition='middle right',
                                 textfont=dict(size=8, color='rgb(0, 0, 255, 0.0)'), hoverinfo='none',
                                 mode='text', showlegend=True,
                                 marker=dict(
                                     sizemode='area',
                                     sizeref=0.1,
                                 )), row=1, col=1)

        fig.add_trace(
            go.Heatmap(
                x=self.df['identifier'],
                y=self.df['price'],
                z=self.df['size'],
                text=self.df['text'],
                colorscale='icefire_r',
                showscale=False,
                showlegend=True,
                name='BidAsk',
                texttemplate="%{text}",
                textfont={
                    "size": 11,
                    "family": "Courier New"},
                hovertemplate="Price: %{y}<br>Size: %{text}<br>Imbalance: %{z}<extra></extra>",
                xgap=60),
            row=1,
            col=1,
        )

        fig.add_trace(
            go.Scatter(
                x=self.green_hl.index,
                y=self.green_hl['price'],
                name='Candle',
                legendgroup='group',
                showlegend=True,
                line=dict(
                    color='green',
                    width=1.5)),
            row=1,
            col=1,
        )

        fig.add_trace(
            go.Scatter(
                x=self.red_hl.index,
                y=self.red_hl['price'],
                name='Candle',
                legendgroup='group',
                showlegend=False,
                line=dict(
                    color='red',
                    width=1.5)),
            row=1,
            col=1,
        )

        fig.add_trace(
            go.Scatter(
                x=self.green_oc.index,
                y=self.green_oc['price'],
                name='Candle',
                legendgroup='group',
                showlegend=False,
                line=dict(
                    color='green',
                    width=6)),
            row=1,
            col=1,
        )

        fig.add_trace(
            go.Scatter(
                x=self.red_oc.index,
                y=self.red_oc['price'],
                name='Candle',
                legendgroup='group',
                showlegend=False,
                line=dict(
                    color='red',
                    width=6)),
            row=1,
            col=1,
        )

        fig.add_trace(
            go.Heatmap(
                x=self.labels.index,
                y=self.labels['type'],
                z=self.labels['value'],
                colorscale='rdylgn',
                showscale=False,
                showlegend=True,
                name='Parameters',
                text=self.labels['text'],
                texttemplate="%{text}",
                textfont={
                    "size": 10},
                hovertemplate="%{x}<br>%{text}<extra></extra>",
                xgap=4,
                ygap=4),
            row=2,
            col=1,
        )

        fig.update_layout(
            title='Order Book Chart',
            yaxis=dict(title='Price', showgrid=False, range=[ymax, ymin], tickformat='.2f'),
            yaxis2=dict(fixedrange=True, showgrid=False),
            xaxis2=dict(title='Time', showgrid=False),
            xaxis=dict(showgrid=False, range=[xmin, xmax]),
            height=780,
            template='plotly_dark',
            paper_bgcolor='#222', plot_bgcolor='#222',
            dragmode='pan', margin=dict(l=10, r=0, t=40, b=20),
        )

        fig.update_xaxes(
            showspikes=True,
            spikecolor="white",
            spikesnap="cursor",
            spikemode="across",
            spikethickness=0.25,
            tickmode='array',
            tickvals=tickvals,
            ticktext=ticktext,
        )

        fig.update_yaxes(
            showspikes=True,
            spikecolor="white",
            spikesnap="cursor",
            spikemode="across",
            spikethickness=0.25,
        )

        fig.update_layout(spikedistance=1000, hoverdistance=100)

        config = {
            'modeBarButtonsToRemove': ['zoomIn', 'zoomOut', 'zoom', 'autoScale'],
            'scrollZoom': True,
            'displaylogo': False,
            'modeBarButtonsToAdd': ['drawline',
                                    'drawopenpath',
                                    'drawclosedpath',
                                    'drawcircle',
                                    'drawrect',
                                    'eraseshape'
                                    ]
        }

        fig.show(config=config)
