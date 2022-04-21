import altair as alt
from sklearn.linear_model import LogisticRegression
from autopilot.data.subject import Subject
import numpy as np
from autopilot.utils.common import coerce_discrete
import pandas as pd


def calc_psychometric(data, var_x, var_y='response'):
    """
    Calculate a psychometric curve (logistic regression of var_y on var_x)

    Args:
        data (:class:`pandas.DataFrame`): Subject data
        var_x (str): name of column to use as the discriminand
        var_y (str): name of the column for the response, usually 'response'

    Returns:
        params (tup): parameters for logistic function
    """
    data = data[[var_x, var_y]].copy()

    try:
        if not all(data[var_y].str.isnumeric()):
            data = coerce_discrete(data, var_y)
    except AttributeError:
        # if w can't use the .str accessor, then it's probs a number
        pass



    log_regress = LogisticRegression()
    try:
        log_regress.fit(data[var_x], data[var_y])
    except ValueError:
        # need to have X data be 2d
        log_regress.fit(data.as_matrix(columns=[var_x]), data[var_y])

    return log_regress


def plot_psychometric(subject_protocols):
    """
    Plot psychometric curves for selected subjects, steps, and variables

    Typically called by :meth:`.Terminal.plot_psychometric`.

    Args:
        subject_protocols (list): A list of tuples, each with

            * subject_id (str)
            * step_name (str)
            * variable (str)

    Returns:
        :class:`altair.Chart`
    """

    for subject, step, var, n_trials in subject_protocols:
        # load subject dataframe and subset
        asub = Subject(subject)
        sub_df = asub.get_trial_data(step)

        if n_trials>0:
            sub_df = sub_df[-n_trials:]

        # pdb.set_trace()

        sub_df = coerce_discrete(sub_df, 'response')
        logit = calc_psychometric(sub_df, var)

        # generate points to plot regression fit
        logit_x = np.linspace(sub_df[var].min(), sub_df[var].max(), 100).reshape(-1,1)
        logit_y = logit.predict_proba(logit_x)

        # pdb.set_trace()
        this_logit_df = pd.DataFrame({'x': logit_x[:,0], 'y':logit_y[:,1]})
        this_logit_df['subject'] = subject
        this_logit_df['type'] = 'log_regression'

        try:
            logit_df = pd.concat([logit_df, this_logit_df])
        except NameError:
            logit_df = this_logit_df

        # and also mean accuracy by var
        sub_df_sum = sub_df.groupby(var).mean().reset_index()[[var, 'response']]
        sub_df_sum['subject'] = subject
        sub_df_sum['type'] = 'responses'
        sub_df_sum.rename(columns={var:'x', 'response':'y'}, inplace=True)

        try:
            sum_df = pd.concat([sum_df, sub_df_sum])
        except NameError:
            sum_df = sub_df_sum

    # combine dataframes
    combo_df = pd.concat([sum_df, logit_df])

    acc_points = alt.Chart().encode(
        alt.X('x:Q',scale=alt.Scale(type='sqrt'), title=var),
        y=alt.Y('y:Q',title="mean response")
    ).transform_filter(
        alt.FieldEqualPredicate('responses', 'type')
    ).mark_point()

    log_curves = alt.Chart().encode(
        alt.X('x:Q',scale=alt.Scale(type='sqrt'), title=var),
        y=alt.Y('y:Q',title="mean response")
    ).transform_filter(
        alt.FieldEqualPredicate('log_regression', 'type')
    ).mark_line()

    combo = alt.layer(acc_points + log_curves, data=combo_df).facet(row='subject:N')
    #combo.sav
    return combo

    #combo.serve()

    # acc_points.serve()








