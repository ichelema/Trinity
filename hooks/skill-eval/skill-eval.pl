#!/usr/bin/env perl
# Skill Evaluation Engine v3.0 — port Perl di skill-eval.py.
# Stessa logica e stesso output del .py: regex native + JSON::PP (core).

use strict;
use warnings;
use feature 'unicode_strings';
use JSON::PP ();

use Cwd qw(abs_path);
use File::Basename qw(dirname);

# JSON::PP vuole byte raw in input/emette byte raw in output.
binmode STDIN,  ":raw";
binmode STDOUT, ":raw";

my $script = $0;
$script =~ s{\\}{/}g;
my $resolved = abs_path($script) // $script;
my $SCRIPT_DIR = dirname($resolved);
my $RULES_PATH = "$SCRIPT_DIR/skill-rules.json";
my $SKILLS_DIR = "$SCRIPT_DIR/../../skills";

sub is_skill_disabled {
    my ($name) = @_;
    my $d = "$SKILLS_DIR/$name";
    return (-d $d) && !(-e "$d/SKILL.md");
}

sub load_rules {
    my $raw;
    open(my $fh, "<:raw", $RULES_PATH) or do {
        print STDERR "Failed to load skill rules: $!\n";
        exit 0;
    };
    local $/;
    $raw = <$fh>;
    close $fh;
    return JSON::PP::decode_json($raw);
}

sub extract_file_paths {
    my ($prompt) = @_;
    my %seen;

    while ($prompt =~ /(?:^|\s|["'`])([\w\-.\/\\:]+\.(?:py|rb|sh|xlsx?|csv|excalidraw|md|json|lua|toml|cr|go|rs|png|svg|ya?ml|pdf|epub|docx|mobi|azw3?|rtf))\b/gi) {
        $seen{$1} = 1;
    }
    while ($prompt =~ /(?:^|\s|["'`])((?:data|test|logs|script|sound|\.claude|\.github)[\\\/][\w\-.\/\\]+)/gi) {
        $seen{$1} = 1;
    }
    while ($prompt =~ /["'`]([\w\-.\/\\:]+[\/\\][\w\-.\/\\]+)["'`]/g) {
        $seen{$1} = 1;
    }

    return [ keys %seen ];
}

sub matches_pattern {
    my ($text, $pattern, $flags) = @_;
    $flags = "i" unless defined $flags;
    my $mod = (index($flags, "i") >= 0) ? "i" : "";
    my $re = eval { $mod ? qr{(?$mod:$pattern)} : qr{(?:$pattern)} };
    return 0 if $@;
    return ($text =~ $re) ? 1 : 0;
}

sub matches_glob {
    my ($file_path, $glob_pattern) = @_;
    my $normalized = $file_path;
    $normalized =~ s{\\}{/}g;
    my $regex = $glob_pattern;
    $regex =~ s{\.}{\\.}g;
    $regex =~ s{\?}{.}g;
    $regex =~ s{\*\*/}{<<<DOUBLESTARSLASH>>>}g;
    $regex =~ s{\*\*}{<<<DOUBLESTAR>>>}g;
    $regex =~ s{\*}{[^/]*}g;
    $regex =~ s{<<<DOUBLESTARSLASH>>>}{(.*/)?}g;
    $regex =~ s{<<<DOUBLESTAR>>>}{.*}g;
    my $re = eval { qr{^$regex$}i };
    return 0 if $@;
    return ($normalized =~ $re) ? 1 : 0;
}

sub match_directory_mapping {
    my ($file_path, $mappings) = @_;
    my $normalized = $file_path;
    $normalized =~ s{\\}{/}g;
    for my $dir (keys %$mappings) {
        my $skill = $mappings->{$dir};
        if ($normalized eq $dir || index($normalized, "$dir/") == 0) {
            return $skill;
        }
    }
    return undef;
}

sub evaluate_skill {
    my ($skill_name, $skill, $prompt, $prompt_lower, $file_paths, $rules) = @_;
    my $triggers = $skill->{triggers} // {};
    my $exclude  = $skill->{excludePatterns} // [];
    my $priority = $skill->{priority} // 5;
    my $scoring  = $rules->{scoring};

    return undef if is_skill_disabled($skill_name);

    my $score = 0;
    my @reasons;

    for my $ep (@$exclude) {
        return undef if matches_pattern($prompt_lower, $ep);
    }

    if ($triggers->{keywords}) {
        for my $kw (@{$triggers->{keywords}}) {
            if (index($prompt_lower, lc($kw)) >= 0) {
                $score += $scoring->{keyword};
                push @reasons, "keyword \"$kw\"";
            }
        }
    }

    if ($triggers->{keywordPatterns}) {
        for my $pat (@{$triggers->{keywordPatterns}}) {
            if (matches_pattern($prompt_lower, $pat)) {
                $score += $scoring->{keywordPattern};
                push @reasons, "pattern /$pat/";
            }
        }
    }

    if ($triggers->{intentPatterns}) {
        for my $pat (@{$triggers->{intentPatterns}}) {
            if (matches_pattern($prompt_lower, $pat)) {
                $score += $scoring->{intentPattern};
                push @reasons, "intent detected";
                last;
            }
        }
    }

    if ($triggers->{contextPatterns}) {
        for my $pat (@{$triggers->{contextPatterns}}) {
            if (index($prompt_lower, lc($pat)) >= 0) {
                $score += $scoring->{contextPattern};
                push @reasons, "context \"$pat\"";
            }
        }
    }

    if ($triggers->{pathPatterns} && @$file_paths) {
        for my $fp (@$file_paths) {
            for my $pat (@{$triggers->{pathPatterns}}) {
                if (matches_glob($fp, $pat)) {
                    $score += $scoring->{pathPattern};
                    push @reasons, "path \"$fp\"";
                    last;
                }
            }
        }
    }

    if ($rules->{directoryMappings} && @$file_paths) {
        for my $fp (@$file_paths) {
            my $mapped = match_directory_mapping($fp, $rules->{directoryMappings});
            if (defined($mapped) && $mapped eq $skill_name) {
                $score += $scoring->{directoryMatch};
                push @reasons, "directory mapping";
                last;
            }
        }
    }

    if ($triggers->{contentPatterns}) {
        for my $pat (@{$triggers->{contentPatterns}}) {
            if (matches_pattern($prompt, $pat)) {
                $score += $scoring->{contentPattern};
                push @reasons, "code pattern detected";
                last;
            }
        }
    }

    if ($score > 0) {
        my %seen;
        my @uniq = grep { !$seen{$_}++ } @reasons;
        return {
            name     => $skill_name,
            score    => $score,
            reasons  => \@uniq,
            priority => $priority,
        };
    }
    return undef;
}

sub get_related_skills {
    my ($matches, $skills) = @_;
    my %matched = map { $_->{name} => 1 } @$matches;
    my %related;
    for my $m (@$matches) {
        my $skill = $skills->{$m->{name}} // {};
        for my $rn (@{$skill->{relatedSkills} // []}) {
            $related{$rn} = 1 if !$matched{$rn} && !is_skill_disabled($rn);
        }
    }
    return [ keys %related ];
}

sub format_confidence {
    my ($score, $min) = @_;
    return "HIGH"   if $score >= $min * 3;
    return "MEDIUM" if $score >= $min * 2;
    return "LOW";
}

sub evaluate {
    my ($prompt) = @_;
    my $rules  = load_rules();
    my $config = $rules->{config};
    my $skills = $rules->{skills};

    my $prompt_lower = lc($prompt);
    my $file_paths   = extract_file_paths($prompt);

    my @matches;
    for my $name (keys %$skills) {
        my $m = evaluate_skill($name, $skills->{$name}, $prompt, $prompt_lower, $file_paths, $rules);
        if ($m && $m->{score} >= $config->{minConfidenceScore}) {
            push @matches, $m;
        }
    }

    return "" unless @matches;

    @matches = sort { $b->{score} <=> $a->{score} || $a->{priority} <=> $b->{priority} } @matches;

    my $max  = $config->{maxSkillsToShow};
    my $last = ($max - 1) < $#matches ? ($max - 1) : $#matches;
    my @top = @matches[0 .. $last];
    my $related = get_related_skills(\@top, $skills);

    my $context = "SKILL ACTIVATION REQUIRED\n\n";

    if (@$file_paths) {
        $context .= "Detected file paths: " . join(", ", @$file_paths) . "\n\n";
    }

    $context .= "Matched skills (ranked by relevance):\n";

    my $i = 1;
    for my $m (@top) {
        my $confidence = format_confidence($m->{score}, $config->{minConfidenceScore});
        my $nm = $m->{name};
        $context .= "$i. $nm ($confidence confidence)\n";
        if ($config->{showMatchReasons} && @{$m->{reasons}}) {
            my $r = $m->{reasons};
            my @first3 = @$r > 3 ? @$r[0 .. 2] : @$r;
            $context .= "   Matched: " . join(", ", @first3) . "\n";
        }
        $i++;
    }

    if (@$related) {
        $context .= "\nRelated skills to consider: " . join(", ", @$related) . "\n";
    }

    $context .= "\nBefore implementing, you MUST:\n";
    $context .= "1. EVALUATE: State YES/NO for each skill with brief reasoning\n";
    $context .= "2. ACTIVATE: Invoke the Skill tool for each YES skill\n";
    $context .= "3. IMPLEMENT: Only proceed after skill activation\n";
    $context .= "\nExample evaluation:\n";
    my $n0 = $top[0]->{name};
    $context .= "- $n0: YES - [your reasoning]\n";
    if (@top > 1) {
        my $n1 = $top[1]->{name};
        $context .= "- $n1: NO - [your reasoning]\n";
    }
    $context .= "\nDO NOT skip this step. Invoke relevant skills NOW.";

    return $context;
}

sub main {
    my $input = do { local $/; <STDIN> };

    my $prompt = "";
    my $data = eval { JSON::PP::decode_json($input) };
    if (defined $data) {
        $prompt = $data->{prompt} // "";
    } else {
        $prompt = $input;
    }

    exit 0 if $prompt !~ /\S/;

    my $output = eval { evaluate($prompt) };
    if ($@) {
        print STDERR "Skill evaluation failed: $@\n";
        exit 0;
    }

    if ($output) {
        my $hook_output = JSON::PP::encode_json({
            hookSpecificOutput => {
                hookEventName     => "UserPromptSubmit",
                additionalContext => $output,
            },
        });
        print $hook_output;
    }

    exit 0;
}

main();
