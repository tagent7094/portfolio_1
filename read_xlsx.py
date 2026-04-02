import pandas as pd
df = pd.read_excel('C:/Users/Akshit/Downloads/Viral posts - Data - Akshit.xlsx')
with open('_xlsx_info.txt', 'w', encoding='utf-8') as f:
    f.write(f'Shape: {df.shape}\n')
    f.write(f'Columns: {list(df.columns)}\n---\n')
    for i, row in df.head(3).iterrows():
        f.write(f'\nRow {i}:\n')
        for col in df.columns:
            val = str(row[col])[:150].replace('\n', ' ')
            f.write(f'  {col}: {val}\n')
    f.write(f'\nTotal rows: {len(df)}\n')
