import os

def parse_country_colors(countries_file, output_file):
    country_colors = {}
    
    # Read the 00_countries.txt file to map tags to country files
    with open(countries_file, 'r') as file:
        for line in file:
            if '=' in line and not line.strip().startswith('#'):
                tag, country_file = line.split('=')
                tag = tag.strip()
                country_file = country_file.strip().strip('"')
                country_colors[tag] = country_file
    
    # Now, parse each country file to extract the color
    for tag, country_file in country_colors.items():
        print(tag, " ", country_file)
        if os.path.exists(country_file):
            with open(country_file, 'r') as cf:
                for line in cf:
                    if line.strip().startswith('color = {'):
                        # Extract the color values
                        color = line.strip().split('{')[1].split('}')[0].strip()
                        country_colors[tag] = color
                        break
    
    # Write the results to the output file
    with open(output_file, 'w') as outfile:
        for tag, color in country_colors.items():
            outfile.write(f"{tag} = {color}\n")

# Path to the 00_countries.txt file
countries_file = '00_countries.txt'
# Output file to store the country colors
output_file = 'country_colors.txt'

# Generate the country colors file
parse_country_colors(countries_file, output_file)

print(f"Country colors have been written to {output_file}")


