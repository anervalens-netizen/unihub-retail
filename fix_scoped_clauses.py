import re

with open('backend/routers/dashboard.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if 'scoped_clauses(' in line:
        # Check what the params array is called
        # Usually it's `params`, or `metric_params`, or `promo_params`
        # Let's look up to 15 lines above for the name of the params variable
        param_var = "params"
        for j in range(i-1, max(-1, i-25), -1):
            if 'metric_params' in lines[j] or 'metric_positions' in lines[j]:
                param_var = "metric_params"
                break
            if 'promo_params' in lines[j] or 'promo_positions' in lines[j]:
                param_var = "promo_params"
                break
            if 'incentive_params' in lines[j] or 'incentive_positions' in lines[j]:
                param_var = "incentive_params"
                break
            if 'receipt_scope_params' in line and 'receipt_query_clauses' in line:
                param_var = "params"
                break
            if 'sales_params' in lines[j] or 'sales_positions' in lines[j]:
                param_var = "sales_params"
                break
            if 'agent_params' in lines[j] or 'agent_positions' in lines[j]:
                param_var = "agent_params"
                break
            if '_params,' in lines[j] and 'scoped_params' in lines[j]:
                # find prefix
                m = re.search(r'([a-z_]+)params\s*,', lines[j])
                if m:
                    param_var = m.group(1) + "params"
        
        # Now find the closing parenthesis of scoped_clauses
        # It could be many lines down.
        # Find the line with `)` that closes this call
        start_i = i
        open_parens = 0
        while i < len(lines):
            open_parens += lines[i].count('(')
            open_parens -= lines[i].count(')')
            if open_parens == 0:
                # This is the closing parenthesis!
                # If there's already param_floor, do nothing
                call_text = "".join(lines[start_i:i+1])
                if "param_floor=" not in call_text:
                    # Insert before the closing parenthesis
                    # Find the last line, insert param_floor=len(param_var)
                    last_line = lines[i]
                    idx = last_line.rfind(')')
                    if last_line[idx-1] == ' ' or last_line[idx-1] == '\n':
                        # It's on a new line probably
                        pass
                    
                    # A better way: just replace `\n    )` with `,\n        param_floor=len({param_var}),\n    )`
                    # Wait, some end with `scope_base_alias="agg",\n    )`
                    
                    if lines[i-1].strip().endswith(','):
                        lines[i-1] = lines[i-1].rstrip() + f"\n        param_floor=len({param_var}),\n"
                    else:
                        lines[i-1] = lines[i-1].rstrip() + f",\n        param_floor=len({param_var}),\n"
                break
            i += 1
    new_lines.append(lines[i])
    i += 1

with open('backend/routers/dashboard.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
