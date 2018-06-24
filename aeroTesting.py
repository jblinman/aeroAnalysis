import pandas as pd
import os
import json
import matplotlib.pyplot as plt
from datetime import date
import ntpath

class Probe(object):
    def __init__(self, data_path, knownColumns = False):
        self.data_path = data_path
        ret = self.ensure_file(self.data_path)
        self.data = pd.read_csv(self.data_path, sep='\t', engine='python', header=None, skiprows=1)
        self.colDict = self.label_columns(knownColumns = knownColumns)
        self.cp = self.get_cp()
        
    @staticmethod
    def ensure_file(path):
        if os.path.isfile(path):
            return True
        else:
            print("Error: file {} does not exist".format(path))
            return False
    
    
    
    #################
    ## DATA INGEST ##
    #################
    
    def label_columns(self, knownColumns = False):
        if knownColumns:
            colDict = knownColumns
            self.known_columns(colDict)
        else:
            
            if self.ensure_file('knownHeaders.txt'):
                #print('file exists')
                with open('knownHeaders.txt') as infile:
                    allFormats = json.load(infile)
                selected = False
                while selected == False:
                    print('Known headers:')
                    for key in allFormats.keys():
                        print(key)
                    name = input("Choose an existing header or type NO:")
                    if name == 'NO':
                        selected = True
                    else:
                        try:
                            colDict = allFormats[name]
                            print(colDict)
                            knownColumns=True
                            selected = True
                        except:
                            print('Unknown header.')
            else:
                allFormats = {}
            if knownColumns:
                #print('applying preselected column headers')
                self.known_columns(colDict)
            else:
                colDict = self.unknown_columns()
                #print(colDict)
                name = input("What would you like to save this header as? If you do not want to save, type NO.")
                if name == 'NO':
                    pass
                else:
                    allFormats[name] = colDict
                    with open('knownHeaders.txt', 'w') as outfile:
                        json.dump(allFormats, outfile)
        return colDict
    
    def unknown_columns(self):
        # query the user to determine which column is which
        colDict = {}
        print(self.data.head())
        cols = {
            'angle': 'angle', 
            'tunnel reference total pressure': 'tunnel_ref_total_pressure', 
            'unit under test total pressure': 'uut_total_pressure',
            'tunnel reference static pressure': 'tunnel_ref_static_pressure',
            'unit under test static pressure 1': 'uut_static_pressure1',
            'unit under test static pressure 2': 'uut_static_pressure2',
            'date': 'date',
            'time': 'time',
            'temperature in F': 'tempF'
        }
        for key in sorted(cols.keys()):
            col = input("Which column number contains the {}?".format(key))
            col = int(col)
            self.data.rename(index=str, columns={col: cols[key]}, inplace=True)
            colDict[col]=cols[key]
            print('')
            print(self.data.head())
        return colDict
    
    def known_columns(self, colDict):
        for key in colDict.keys():
            self.data.rename(index=str, columns={int(key): colDict[key]}, inplace=True)
        return colDict
    
    #######################
    ## DATA MANIPULATION ##
    #######################
    
    def get_cp(self):
        # group data by angle
        # in each of 5 pressure columns, take average over one angle and 15 sec
        df = self.data[['tunnel_ref_total_pressure', 'uut_static_pressure1', 'uut_static_pressure2', 'uut_total_pressure','tunnel_ref_static_pressure','angle']]
        # normalize angle column
        df['angle'] = df['angle'].apply(self.normalize_angle)
        #df.loc['angle'] = df['angle'].apply(self.normalize_angle)

        mean_df = df.groupby('angle').mean()
        #mean_df.head()
        # normalize by drift data
        # take tunnel_ref_total_pressure, uut_total_pressure (unit under test), take average of each,
        # take difference to find offset to apply to all other uut_total_pressure data (for all angles)
        offset_total_pressure = mean_df['tunnel_ref_total_pressure'][mean_df.index=='Drift Data'].values[0] - mean_df['uut_total_pressure'][mean_df.index=='Drift Data'].values[0]
        mean_df['uut_total_pressure'] = mean_df['uut_total_pressure'] + offset_total_pressure
        # compare both static pressures to the tunnel_ref_static_pressure and do the same as above
        offset_static_pressure1 = mean_df['tunnel_ref_static_pressure'][mean_df.index=='Drift Data'].values[0] - mean_df['uut_static_pressure1'][mean_df.index=='Drift Data'].values[0]
        mean_df['uut_static_pressure1'] = mean_df['uut_static_pressure1'] + offset_static_pressure1
        offset_static_pressure2 = mean_df['tunnel_ref_static_pressure'][mean_df.index=='Drift Data'].values[0] - mean_df['uut_static_pressure2'][mean_df.index=='Drift Data'].values[0]
        mean_df['uut_static_pressure2'] = mean_df['uut_static_pressure2'] + offset_static_pressure2
        # find impact pressure = tunnel_total - tunnel_static (qc) (do for each angle, do )
        mean_df['impact_pressure'] = mean_df['tunnel_ref_total_pressure'] - mean_df['tunnel_ref_static_pressure']
        # divide all uut pressure normalized averages (one total, two static) by impact pressure (qc)
        # take difference of ref_total and uut_total (similar for static)      
        mean_df['cp_total_pressure'] = (mean_df['tunnel_ref_total_pressure'] - mean_df['uut_total_pressure'])/mean_df['impact_pressure']
        mean_df['cp_static_pressure1'] = (mean_df['tunnel_ref_static_pressure'] - mean_df['uut_static_pressure1'])/mean_df['impact_pressure']
        mean_df['cp_static_pressure2'] = (mean_df['tunnel_ref_static_pressure'] - mean_df['uut_static_pressure2'])/mean_df['impact_pressure']
        return mean_df
    
    @staticmethod
    def normalize_angle(s):
        #TODO: Make this more extensible to other formats
        if 'Drift Data' in s:
            return 'Drift Data'
        else:
            return int(s.split('ATP  at')[-1].split('deg AOA')[0])
    
    
class AeroRepeatability(object):
    def __init__(self, golden_probe_path, uut_probe_path):
        self.golden_probe = Probe(golden_probe_path)
        print(self.golden_probe.colDict)
        self.uut_probe = Probe(uut_probe_path, knownColumns = self.golden_probe.colDict)
        for col in ['cp_total_pressure']:
            self.compare_cp(col)
        for col in ['cp_static_pressure1', 'cp_static_pressure2']:
            self.compare_cp(col, origin_bounds = 0.002)
    
    def compare_cp(self, col, origin_bounds = 0.005):
        #filename = self.uut_probe.data_path
        filename = ntpath.basename(self.uut_probe.data_path)
        if 'total' in col:
            generated_title = 'Total Pressure'
            filename = filename + '-total-'
        elif 'static' in col and '1' in col:
            generated_title = 'Static Pressure 1'
            filename = filename + '-static1-'
        elif 'static' in col and '2' in col:
            generated_title = 'Static Pressure 2'
            filename = filename + '-static2-'
        else:
            generated_title = ''
        filename = filename + '-' + str(date.today())
        # check if passed or failed
        difference = self.uut_probe.cp[col]-self.golden_probe.cp[col]
        difference.drop(labels='Drift Data', inplace=True)
        difference.sort_index()
        
        
        
        pos_mask = difference.index.to_series() >= 0
        neg_mask = difference.index.to_series() < 0
        upper_bound = pd.concat([origin_bounds + difference.index.to_series()[pos_mask]*0.0005, origin_bounds - difference.index.to_series()[neg_mask]*0.0005])
        upper_bound.sort_index()
        lower_bound = pd.concat([-origin_bounds - difference.index.to_series()[pos_mask]*0.0005, -origin_bounds + difference.index.to_series()[neg_mask]*0.0005])
        lower_bound.sort_index()
        
        # vector of boolean values describing if that point passed or failed
        pf_bool = (upper_bound - difference < 0) | (difference - lower_bound < 0)# true if out of bounds
        pf = pd.DataFrame(['P']*len(pf_bool.index), index = pf_bool.index)
        pf[pf_bool] = 'F'
        
        to_save = pd.concat([difference, upper_bound, lower_bound, pf], axis=1)
        to_save.sort_index()
        to_save.to_csv(filename + '.csv', header=['dcp', 'upper_bound', 'lower_bound', 'pass_fail'], index_label='AOA')
        
        if any(upper_bound - difference < 0):
            passFail = 'FAIL'
        elif any(difference - lower_bound < 0):
            passFail = 'FAIL'
        else:
            passFail = 'PASS'
        
        neg_mask = difference.index.to_series() <= 0
        
        plt.figure(figsize=(8, 6), dpi=80)
        plt.scatter(difference.index, difference, color='blue')

        #plt.plot(upper_bound.index, upper_bound, linestyle='dashed', color='red')
        plt.plot(difference.index[pos_mask], origin_bounds + difference.index.to_series()[pos_mask]*0.0005, linestyle='dashed', color='red')
        plt.plot(difference.index[pos_mask], -origin_bounds - difference.index.to_series()[pos_mask]*0.0005, linestyle='dashed', color='red')
        plt.plot(difference.index[neg_mask], origin_bounds - difference.index.to_series()[neg_mask]*0.0005, linestyle='dashed', color='red')
        plt.plot(difference.index[neg_mask], -origin_bounds + difference.index.to_series()[neg_mask]*0.0005, linestyle='dashed', color='red')
        plt.xlabel('AOA (deg)')
        plt.ylabel('$\Delta$P / $q_c$')
        plt.title(generated_title + '\n ' + passFail)

        #plt.show()
        plt.savefig(filename + '.png')
        plt.close()
        return
    
      