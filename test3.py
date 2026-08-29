import os, openpyxl  
for f in os.listdir('bench/data/gaia/attachments'):  
    if f.endswith('.xlsx'):  
        wb = openpyxl.load_workbook(os.path.join('bench/data/gaia/attachments', f), data_only=True)  
        ws = wb.active  
        rows = list(ws.iter_rows(values_only=True, max_row=3))  
        print(f, rows[0] if rows else 'empty')  
