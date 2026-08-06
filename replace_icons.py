import os

replacements = {
    '🔍': '<i class="fa-solid fa-magnifying-glass"></i>',
    '▶': '<i class="fa-solid fa-play"></i>',
    'ℹ': '<i class="fa-solid fa-circle-info"></i>',
    '🎬': '<i class="fa-solid fa-clapperboard"></i>',
    '🎭': '<i class="fa-solid fa-masks-theater"></i>',
    '📸': '<i class="fa-solid fa-camera"></i>',
    '🏷️': '<i class="fa-solid fa-tags"></i>',
    '🌍': '<i class="fa-solid fa-globe"></i>',
    '📺': '<i class="fa-solid fa-tv"></i>',
    '🏢': '<i class="fa-solid fa-building"></i>',
    '💰': '<i class="fa-solid fa-sack-dollar"></i>',
    '💸': '<i class="fa-solid fa-money-bill-wave"></i>',
    '🔥': '<i class="fa-solid fa-fire"></i>',
    '👥': '<i class="fa-solid fa-users"></i>',
    '🔗': '<i class="fa-solid fa-link"></i>',
    '⭐': '<i class="fa-solid fa-star"></i>',
    '🌐': '<i class="fa-solid fa-globe"></i>',
    '💡': '<i class="fa-solid fa-lightbulb"></i>',
    '💬': '<i class="fa-solid fa-comment-dots"></i>',
    '🚪': '<i class="fa-solid fa-door-open"></i>',
    '⏭': '<i class="fa-solid fa-forward-step"></i>',
    '⏮': '<i class="fa-solid fa-backward-step"></i>'
}

files = ['app/web/templates/queen.html', 'app/web/templates/vip_detail.html']

for file in files:
    if os.path.exists(file):
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for emoji, icon in replacements.items():
            content = content.replace(emoji, icon)
            
        with open(file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Replaced in {file}')
